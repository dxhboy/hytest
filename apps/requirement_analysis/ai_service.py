"""
AI 模型服务：测试用例生成 / 评审 / 改进的提示词构建与结果后处理。

从 models.py 迁出；HTTP 调用层统一走 apps.core.llm.LLMClient。
为兼容历史导入，apps.requirement_analysis.models 仍可 `from .models import AIModelService`（惰性转发）。
"""
import logging
from typing import Any, AsyncIterator, Dict, List

from apps.core.llm import LLMClient, LLMError, LLMTimeoutError

from .models import AIModelConfig, KnowledgeDocument, ProjectSkill, TestCaseGenerationTask

logger = logging.getLogger(__name__)

# 大文档生成耗时较长，读取超时放宽到 900 秒（15 分钟）
GENERATION_READ_TIMEOUT = 900.0


class AIModelService:
    """AI模型服务类"""

    @staticmethod
    def _build_knowledge_context(task) -> tuple:
        """
        根据任务所属项目，检索 Skills 和知识库文档，
        返回 (extra_system, extra_user) 用于注入提示词。
        """
        extra_system = ""
        extra_user = ""

        if not task.project_id:
            return extra_system, extra_user

        try:
            skill = ProjectSkill.objects.filter(project_id=task.project_id).first()
            if skill and skill.content and skill.content.strip():
                extra_system = "\n\n## 项目测试规范\n" + skill.content
        except Exception as e:
            logger.warning("_build_knowledge_context: skill lookup failed: %s", e)

        try:
            chunks = KnowledgeDocument.search(
                query=task.requirement_text,
                project_id=task.project_id,
                top_k=3
            )
            if chunks:
                extra_user = "## 参考知识库\n" + "\n---\n".join(chunks) + "\n\n"
        except Exception as e:
            logger.warning("_build_knowledge_context: knowledge search failed: %s", e)

        return extra_system, extra_user

    @staticmethod
    def _client(config: AIModelConfig) -> LLMClient:
        """构建统一 LLM 客户端（沿用原 URL 智能补全规则与 15 分钟读取超时）"""
        return LLMClient(config, read_timeout=GENERATION_READ_TIMEOUT, auto_version=True)

    @staticmethod
    async def call_openai_compatible_api(
            config: AIModelConfig,
            messages: List[Dict[str, str]],
            max_tokens: int = None
    ) -> Dict[str, Any]:
        """
        调用OpenAI兼容格式的API（bedrock_claude 由 LLMClient 路由到 BedrockAdapter）

        Args:
            config: AI模型配置
            messages: 消息列表
            max_tokens: 可选的最大token数，如果不指定则使用config.max_tokens

        Returns:
            API响应字典
        """
        client = AIModelService._client(config)
        if not client.config.is_bedrock:
            logger.info(f"=== API调用详情 ===")
            logger.info(f"原始base_url: {config.base_url}")
            logger.info(f"模型名称: {config.model_name}")

        try:
            # stream=False 显式发送，与迁移前请求体一致
            result = await client.achat(messages, max_tokens=max_tokens, stream=False)
            logger.info(f"API调用成功，响应内容: {str(result)[:200]}...")
            return result
        except LLMError as e:
            if client.config.is_bedrock:
                # Bedrock 适配器自带错误前缀，保持原样抛出
                raise Exception(e.message)
            provider_name = config.get_model_type_display()
            if e.status_code is not None:
                error_msg = f"{provider_name} API返回错误 {e.status_code}: {e.body}"
                logger.error(error_msg)
                raise Exception(error_msg)
            if isinstance(e, LLMTimeoutError):
                logger.error(f"{provider_name} API请求超时: {e.message}")
                raise Exception(f"{provider_name} API请求超时，请稍后再试或检查网络连接")
            logger.error(f"{provider_name} API调用失败: {e.message}")
            raise Exception(f"{provider_name} API调用失败: {e.message}")

    @staticmethod
    async def call_deepseek_api(config: AIModelConfig, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """调用DeepSeek API (兼容OpenAI格式)"""
        return await AIModelService.call_openai_compatible_api(config, messages)

    @staticmethod
    async def call_qwen_api(config: AIModelConfig, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """调用千问API (兼容OpenAI格式)"""
        return await AIModelService.call_openai_compatible_api(config, messages)

    @staticmethod
    async def call_openai_compatible_api_stream(
            config: AIModelConfig,
            messages: List[Dict[str, str]],
            callback=None,
            max_tokens: int = None
    ) -> AsyncIterator[str]:
        """
        流式调用OpenAI兼容格式的API，支持自动续写
        """
        if config.model_type == 'bedrock_claude':
            # BedrockAdapter 的 callback 传入的是累计全文，而生成流水线的回调按增量追加
            # （task.stream_buffer += chunk），直接透传会导致内容重复；这里改为按增量回调，与 OpenAI 兼容路径一致
            from .bedrock_adapter import BedrockAdapter
            async for chunk in BedrockAdapter.call_stream(config, messages, None, max_tokens):
                if callback:
                    await callback(chunk)
                yield chunk
            return

        client = AIModelService._client(config)

        # 续写控制
        current_messages = list(messages)  # 浅拷贝
        continuation_count = 0
        MAX_CONTINUATIONS = 5  # 最大续写次数，防止死循环

        while continuation_count <= MAX_CONTINUATIONS:
            logger.info(f"发起流式请求 (第{continuation_count + 1}次), messages数量: {len(current_messages)}")

            chunk_content_buffer = ""  # 本次请求生成的完整内容缓存
            finish_reason = None

            try:
                async for delta in client.astream(current_messages, max_tokens=max_tokens):
                    if delta.finish_reason:
                        finish_reason = delta.finish_reason
                    if delta.content:
                        chunk_content_buffer += delta.content
                        if callback:
                            await callback(delta.content)
                        yield delta.content
            except Exception as e:
                logger.error(f"流式请求异常: {e}")
                # 如果是超时或其他网络错误，可能需要重试机制，这里暂时直接抛出
                raise

            # 本次请求结束，检查 finish_reason
            if finish_reason == 'length':
                logger.warning(
                    f"检测到生成被截断 (finish_reason='length')，准备自动续写。当前已续写 {continuation_count} 次。")
                continuation_count += 1

                # 将本次生成的内容作为 assistant 回复加入历史
                # 注意：如果之前已经有assistant消息，需要追加内容而不是新增消息
                if current_messages[-1]['role'] == 'assistant':
                    current_messages[-1]['content'] += chunk_content_buffer
                else:
                    current_messages.append({"role": "assistant", "content": chunk_content_buffer})

                # 只有当上一条不是user的续写指令时，才添加新的user指令
                # 防止多次续写时堆叠重复的 user 指令
                if current_messages[-1]['role'] != 'user':
                    current_messages.append(
                        {"role": "user", "content": "请继续输出剩余的内容，不要重复已输出的部分，紧接着上文继续。"})
                continue

            logger.info(f"流式生成正常结束 (finish_reason={finish_reason})")
            break

    @staticmethod
    async def generate_test_cases(task: TestCaseGenerationTask) -> str:
        """生成测试用例"""
        from asgiref.sync import sync_to_async
        extra_system, extra_user = await sync_to_async(
            AIModelService._build_knowledge_context
        )(task)
        writer_prompt = task.writer_prompt_config.content + extra_system

        # 构建更明确的用户提示，采用思维链(CoT)引导和细粒度拆分策略
        user_message = (
            f"请深入分析以下需求文档，并设计高覆盖率的测试用例。\n\n"
            f"【生成指令】\n"
            f"1. **数量原则**：请根据需求内容的实际复杂度，自动决定生成用例的数量。务必覆盖所有功能点、异常场景和边界条件，不设数量上限，应写尽写。\n"
            f"2. **深度遍历策略**：\n"
            f"   - 请按文档结构逐章节分析，不要遗漏末尾的功能点。\n"
            f"   - 对每个功能点，必须设计：1个正常场景 + 2-3个异常/边界场景。\n"
            f"3. **拒绝合并**：严禁将多个验证点合并在一条用例中。例如'验证输入框'应拆分为'输入为空'、'输入超长'、'输入特殊字符'等独立用例。\n"
            f"4. **场景扩展库**：\n"
            f"   - 数据完整性（必填项、默认值、数据类型）\n"
            f"   - 业务逻辑约束（状态流转、权限控制、重复操作）\n"
            f"   - 外部接口异常（超时、断网、返回错误）\n"
            f"   - UI交互体验（提示文案、跳转逻辑、防误触）\n"
            f"5. **⚠️ 输出顺序要求（必须严格执行）**：\n"
            f"   - **必须按用例编号从小到大的顺序输出**（如：001, 002, 003...或LOGIN_001, LOGIN_002, LOGIN_003...）\n"
            f"   - **绝对不能跳号、重复或乱序输出**\n"
            f"   - **编号必须连续，中间不能有遗漏**\n"
            f"   - **所有用例必须一次性完整输出，不能中断**\n"
            rf"6. **⚠️ 特殊字符处理（关键）**：\n"
            rf"   - **如果在表格内容（如操作步骤、预期结果）中出现管道符 '|'，请使用HTML实体 '&#124;' 代替**。\n"
            rf"   - **绝对不要使用反斜杠转义（如 '\|'），这会导致输出混乱**。\n"
            rf"   - 示例：应输入 'a&#124;b' 而不是 'a|b' 或 'a\|b'。\n\n"
            f"【需求文档内容】\n{task.requirement_text}"
        )
        if extra_user:
            user_message = extra_user + user_message

        messages = [
            {"role": "system", "content": writer_prompt},
            {"role": "user", "content": user_message}
        ]

        # 所有支持的模型都使用兼容OpenAI的接口
        # 使用配置的max_tokens，不硬编码限制
        response = await AIModelService.call_openai_compatible_api(
            task.writer_model_config,
            messages
            # 不再硬编码max_tokens，使用配置文件中的值（如32000）
        )

        return response['choices'][0]['message']['content']

    @staticmethod
    async def review_test_cases(task: TestCaseGenerationTask, test_cases: str) -> str:
        """评审测试用例"""
        try:
            reviewer_prompt = task.reviewer_prompt_config.content

            # 增强的评审指令
            user_message = (
                f"请对以下生成的测试用例进行严格的专家级评审。\n\n"
                f"【评审重点】\n"
                f"1. **覆盖率漏洞**：请仔细比对用例集是否覆盖了常见的异常场景（如断网、超时、数据冲突）和边界条件。\n"
                f"2. **逻辑严密性**：检查预期结果是否具体、可验证（例如'提示错误'是不够的，需说明具体错误码或文案）。\n"
                f"3. **冗余检查**：指出是否有重复或无效的用例。\n\n"
                f"【待评审用例】\n{test_cases}\n\n"
                f"【输出格式要求】\n"
                f"请输出一份包含评分、问题列表和改进建议的详细评审报告。"
                f"**重要**：输出格式要求紧凑，不要在段落之间添加多余的空行，每个问题点之间用单空行分隔即可，用例展示仍为markdown形式。"
            )

            messages = [
                {"role": "system", "content": reviewer_prompt},
                {"role": "user", "content": user_message}
            ]

            # 所有支持的模型都使用兼容OpenAI的接口
            response = await AIModelService.call_openai_compatible_api(task.reviewer_model_config, messages)

            return response['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"评审测试用例时出错: {e}")
            # 返回一个默认的评审结果
            return f"评审过程中出现错误: {str(e)}\n\n建议：测试用例结构完整，可以使用。"

    @staticmethod
    async def generate_test_cases_stream(
            task: TestCaseGenerationTask,
            callback=None
    ) -> str:
        """
        流式生成测试用例

        Args:
            task: 生成任务对象
            callback: 可选的回调函数，每收到一个chunk就调用，用于实时保存到数据库

        Returns:
            str: 完整的测试用例内容
        """
        from asgiref.sync import sync_to_async
        extra_system, extra_user = await sync_to_async(
            AIModelService._build_knowledge_context
        )(task)
        writer_prompt = task.writer_prompt_config.content + extra_system

        # 构建用户提示
        user_message = (
            f"请深入分析以下需求文档，并设计高覆盖率的测试用例。\n\n"
            f"【生成指令】\n"
            f"1. **数量原则**：请根据需求内容的实际复杂度，自动决定生成用例的数量。务必覆盖所有功能点、异常场景和边界条件，不设数量上限，应写尽写。\n"
            f"2. **深度遍历策略**：\n"
            f"   - 请按文档结构逐章节分析，不要遗漏末尾的功能点。\n"
            f"   - 对每个功能点，必须设计：1个正常场景 + 2-3个异常/边界场景。\n"
            f"3. **拒绝合并**：严禁将多个验证点合并在一条用例中。例如'验证输入框'应拆分为'输入为空'、'输入超长'、'输入特殊字符'等独立用例。\n"
            f"4. **场景扩展库**：\n"
            f"   - 数据完整性（必填项、默认值、数据类型）\n"
            f"   - 业务逻辑约束（状态流转、权限控制、重复操作）\n"
            f"   - 外部接口异常（超时、断网、返回错误）\n"
            f"   - UI交互体验（提示文案、跳转逻辑、防误触）\n"
            f"5. **⚠️ 输出顺序要求（必须严格执行）**：\n"
            f"   - **必须按用例编号从小到大的顺序输出**（如：001, 002, 003...或LOGIN_001, LOGIN_002, LOGIN_003...）\n"
            f"   - **绝对不能跳号、重复或乱序输出**\n"
            f"   - **编号必须连续，中间不能有遗漏**\n"
            f"   - **所有用例必须一次性完整输出，不能中断**\n"
            rf"6. **⚠️ 特殊字符处理（关键）**：\n"
            rf"   - **如果在表格内容（如操作步骤、预期结果）中出现管道符 '|'，请使用HTML实体 '&#124;' 代替**。\n"
            rf"   - **绝对不要使用反斜杠转义（如 '\|'），这会导致输出混乱**。\n"
            rf"   - 示例：应输入 'a&#124;b' 而不是 'a|b' 或 'a\|b'。\n\n"
            f"【需求文档内容】\n{task.requirement_text}"
        )
        if extra_user:
            user_message = extra_user + user_message

        messages = [
            {"role": "system", "content": writer_prompt},
            {"role": "user", "content": user_message}
        ]

        # 流式调用API，确保正确关闭生成器
        # 使用配置的max_tokens，不硬编码限制
        generator = AIModelService.call_openai_compatible_api_stream(
            task.writer_model_config,
            messages,
            callback=callback
            # 不再硬编码max_tokens，使用配置文件中的值（如32000）
        )

        full_content = ""
        chunk_count = 0
        try:
            async for chunk in generator:
                full_content += chunk
                chunk_count += 1
        except Exception as e:
            logger.error(f"流式生成测试用例时出错: {e}")
            raise
        finally:
            # 确保生成器被正确关闭
            try:
                await generator.aclose()
            except Exception as close_error:
                logger.warning(f"关闭generator时出错: {close_error}")

        logger.info(f"流式生成完成: 总chunk数={chunk_count}, 总字符数={len(full_content)}")

        # 统计生成的用例数量
        case_count = full_content.count('TC-') + full_content.count('TEST-') + full_content.count('测试用例')
        logger.info(f"生成用例统计: 约检测到{case_count}个用例编号标记")

        return full_content

    @staticmethod
    async def review_test_cases_stream(
            task: TestCaseGenerationTask,
            test_cases: str,
            callback=None
    ) -> str:
        """
        流式评审测试用例

        Args:
            task: 生成任务对象
            test_cases: 待评审的测试用例
            callback: 可选的回调函数，每收到一个chunk就调用

        Returns:
            str: 完整的评审反馈
        """
        reviewer_prompt = task.reviewer_prompt_config.content

        # 增强的评审指令
        user_message = (
            f"请对以下生成的测试用例进行严格的专家级评审。\n\n"
            f"【评审重点】\n"
            f"1. **覆盖率漏洞**：请仔细比对用例集是否覆盖了常见的异常场景（如断网、超时、数据冲突）和边界条件。\n"
            f"2. **逻辑严密性**：检查预期结果是否具体、可验证（例如'提示错误'是不够的，需说明具体错误码或文案）。\n"
            f"3. **冗余检查**：指出是否有重复或无效的用例。\n\n"
            f"【待评审用例】\n{test_cases}\n\n"
            f"【输出格式要求】\n"
            f"请输出一份包含评分、问题列表和改进建议的详细评审报告。"
            f"**重要**：输出格式要求紧凑，不要在段落之间添加多余的空行，每个问题点之间用单空行分隔即可，用例展示仍为markdown形式。"
        )

        messages = [
            {"role": "system", "content": reviewer_prompt},
            {"role": "user", "content": user_message}
        ]

        # 流式调用API，确保正确关闭生成器
        generator = AIModelService.call_openai_compatible_api_stream(
            task.reviewer_model_config,
            messages,
            callback=callback
        )

        full_content = ""
        chunk_count = 0
        try:
            async for chunk in generator:
                full_content += chunk
                chunk_count += 1
        except Exception as e:
            logger.error(f"流式评审测试用例时出错: {e}")
            return f"评审过程中出现错误: {str(e)}\n\n建议：测试用例结构完整，可以使用。"
        finally:
            # 确保生成器被正确关闭
            try:
                await generator.aclose()
            except Exception as close_error:
                logger.warning(f"关闭generator时出错: {close_error}")

        logger.info(f"流式评审完成: 总chunk数={chunk_count}, 总字符数={len(full_content)}")
        return full_content

    @staticmethod
    async def revise_test_cases_based_on_review(
            task: TestCaseGenerationTask,
            original_test_cases: str,
            review_feedback: str,
            callback=None
    ) -> str:
        """
        根据评审意见改进测试用例

        Args:
            task: 生成任务对象
            original_test_cases: 原始生成的测试用例
            review_feedback: AI评审意见
            callback: 可选的回调函数，每收到一个chunk就调用

        Returns:
            str: 改进后的测试用例
        """
        writer_prompt = task.writer_prompt_config.content

        # 构建改进指令
        user_message = (
            f"请根据以下专家评审意见，改进和完善测试用例。\n\n"
            f"【原始测试用例】\n{original_test_cases}\n\n"
            f"【评审意见】\n{review_feedback}\n\n"
            f"【改进要求】\n"
            f"1. 严格根据评审意见指出的问题进行修改\n"
            f"2. 补充缺失的测试场景\n"
            f"3. 修正不合理的预期结果\n"
            f"4. 删除冗余的测试用例\n"
            f"5. 保持测试用例的格式规范\n"
            f"6. **加粗标记规则（必须严格执行）**：\n"
            f"   **6.1 新增测试用例**：对整个新增的测试用例进行加粗\n"
            f"   - 示例：**TC-004 测试用例标题**\\n**测试步骤：**\\n**1. 步骤内容**\\n**预期结果：**\\n**2. 预期内容**\n"
            f"   - 注意：新增用例的编号、标题、步骤、预期结果等所有内容都要加粗\n"
            f"   **6.2 修改现有用例**：只对被修改的具体部分进行加粗\n"
            f"   - 修改标题：**TC-001 修改后的新标题**（其他内容保持原样）\n"
            f"   - 修改步骤：1. 原步骤\\n2. **修改后的步骤内容**（只有步骤2加粗）\n"
            f"   - 修改预期结果：预期结果：**修改后的预期内容**（只有预期内容加粗）\n"
            f"   - 新增步骤：1. 原步骤\\n**2. 新增的步骤内容**（新增的步骤整体加粗）\n"
            f"   **6.3 注意事项**：\n"
            f"   - 未修改的部分不要加粗\n"
            f"   - 原始测试用例中已经存在的用例，如果没有改动就不要加粗\n"
            f"   - 只有根据评审意见新增或修改的部分才需要加粗\n"
            f"7. **⚠️ 输出顺序要求（必须严格执行）**：\n"
            f"   - **必须按用例编号从小到大的顺序输出**（如：001, 002, 003...或LOGIN_001, LOGIN_002, LOGIN_003...）\n"
            f"   - **绝对不能跳号、重复或乱序输出**\n"
            f"   - **编号必须连续，中间不能有遗漏**\n"
            f"   - **所有用例必须一次性完整输出，不能中断**\n"
            f"8. **必须输出完整**：请确保输出所有改进后的测试用例，不要因为篇幅原因省略任何用例，"
            f"即使是第30条、第40条甚至更多的用例，也必须完整输出。\n"
            f"9. **测试用例编号规则**：新增的测试用例必须按照原有编号规则继续编号（例如原最后一个用例是TC-003，新增的第一个用例应该是TC-004），"
            f"绝不能使用'新增'、'用例1'等作为编号，必须是正式的测试用例编号。\n"
            rf"10. **⚠️ 特殊字符处理（关键）**：\n"
            rf"   - **如果在表格内容（如操作步骤、预期结果）中出现管道符 '|'，请使用HTML实体 '&#124;' 代替**。\n"
            rf"   - **绝对不要使用反斜杠转义（如 '\|'），这会导致输出混乱**。\n"
            rf"   - 示例：应输入 'a&#124;b' 而不是 'a|b' 或 'a\|b'。\n\n"
            f"请直接输出改进后的完整测试用例，不要包含任何说明性文字。"
        )

        messages = [
            {"role": "system", "content": writer_prompt},
            {"role": "user", "content": user_message}
        ]

        # 流式调用API，确保正确关闭生成器
        # 使用配置的max_tokens，不硬编码限制
        generator = AIModelService.call_openai_compatible_api_stream(
            task.writer_model_config,
            messages,
            callback=callback
            # 不再硬编码max_tokens，使用配置文件中的值（如32000）
        )

        full_content = ""
        chunk_count = 0
        try:
            async for chunk in generator:
                full_content += chunk
                chunk_count += 1
        except Exception as e:
            logger.error(f"根据评审意见改进测试用例时出错: {e}")
            # 改进失败时返回原始用例
            return original_test_cases
        finally:
            # 确保生成器被正确关闭
            try:
                await generator.aclose()
            except Exception as close_error:
                logger.warning(f"关闭generator时出错: {close_error}")

        logger.info(f"流式改进完成: 总chunk数={chunk_count}, 总字符数={len(full_content)}")

        # 统计改进后的用例数量
        case_count = full_content.count('TC-') + full_content.count('**TC-') + full_content.count('测试用例')
        logger.info(f"改进用例统计: 约检测到{case_count}个用例编号标记")

        return full_content

    @staticmethod
    def sort_test_cases_by_id(test_cases_content: str) -> str:
        """
        按照测试用例编号排序测试用例内容

        Args:
            test_cases_content: 测试用例内容（字符串）

        Returns:
            str: 排序后的测试用例内容
        """
        if not test_cases_content:
            return test_cases_content

        import re

        # 按行分割内容
        lines = test_cases_content.split('\n')

        # 识别用例块：每个用例从包含编号的行开始
        # 支持多种编号格式：TC-001, TC001, TEST-001, 测试用例1, 1. 等
        case_pattern = re.compile(r'^(#{1,6}\s+)?(?:TC[-_]?\d+|TEST[-_]?\d+|测试用例\d+|\d+[\.\、]\s*[:：]?\s*\S+)',
                                  re.IGNORECASE | re.MULTILINE)

        # 找到所有用例块的起始位置
        case_starts = []
        for i, line in enumerate(lines):
            if case_pattern.match(line):
                case_starts.append(i)

        # 如果没有找到编号，返回原内容
        if len(case_starts) < 2:
            logger.info(f"未检测到足够的用例编号（只找到{len(case_starts)}个），保持原顺序")
            return test_cases_content

        # 提取每个用例块
        case_blocks = []
        for i in range(len(case_starts)):
            start = case_starts[i]
            # 下一个用例的开始位置，或者文件末尾
            end = case_starts[i + 1] if i + 1 < len(case_starts) else len(lines)
            block_lines = lines[start:end]
            block_content = '\n'.join(block_lines)
            case_blocks.append({
                'start': start,
                'content': block_content,
                'first_line': block_lines[0] if block_lines else ''
            })

        # 提取编号用于排序
        def extract_case_id(block):
            first_line = block['first_line']
            # 尝试匹配各种编号格式
            # TC-001, TC001, TEST-001, 测试用例1, 1. xxx 等
            match = re.search(r'(?:TC[-_]?|TEST[-_]?|测试用例)?(\d+)', first_line, re.IGNORECASE)
            if match:
                return int(match.group(1))
            return 0

        # 按编号排序
        try:
            case_blocks.sort(key=extract_case_id)
            logger.info(f"成功对{len(case_blocks)}个测试用例按编号排序")
        except Exception as e:
            logger.warning(f"排序失败: {e}，保持原顺序")

        # 重新组合内容
        sorted_content = '\n'.join([block['content'] for block in case_blocks])

        return sorted_content

    @staticmethod
    def fix_incomplete_last_case(test_cases_content: str) -> str:
        """
        检测并修复不完整的最后一条测试用例

        Args:
            test_cases_content: 测试用例内容

        Returns:
            str: 修复后的测试用例内容
        """
        if not test_cases_content:
            return test_cases_content

        lines = test_cases_content.split('\n')

        # 检查最后几行，找到最后一个表格行
        table_lines = []
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if line.startswith('|') and line.endswith('|'):
                table_lines.insert(0, (i, line))
                # 只检查最后10行
                if len(table_lines) >= 10:
                    break

        if not table_lines:
            return test_cases_content

        # 检查最后一个表格行是否完整（应该有7个|，即7列）
        last_line_index, last_line = table_lines[-1]
        column_count = last_line.count('|')

        # 正常的表格应该有7个|（开头+结尾+5个分隔符）
        if column_count < 7:
            logger.warning(f"检测到最后一条用例不完整: 只有{column_count}列，应该是7列")
            # 删除不完整的最后一条用例
            # 找到完整的上一条用例
            for i in range(len(table_lines) - 2, -1, -1):
                prev_index, prev_line = table_lines[i]
                if prev_line.count('|') >= 7:
                    # 截断到上一条完整用例的位置
                    fixed_content = '\n'.join(lines[:prev_index + 1])
                    logger.info(f"已删除不完整的最后一条用例，保留了{prev_index + 1}行")
                    return fixed_content

            # 如果找不到完整的上一条，直接删除最后5行
            fixed_content = '\n'.join(lines[:-5])
            logger.info(f"删除最后5行不完整的内容")
            return fixed_content

        return test_cases_content

    @staticmethod
    def renumber_test_cases(test_cases_content: str) -> str:
        """
        重新编号测试用例，使其编号连续

        Args:
            test_cases_content: 测试用例内容（字符串）

        Returns:
            str: 重新编号后的测试用例内容
        """
        if not test_cases_content:
            return test_cases_content

        import re

        lines = test_cases_content.split('\n')

        # 找到表格分隔线
        separator_line = None
        separator_index = -1
        for i, line in enumerate(lines):
            if line.strip().startswith('|') and '|' in line and '---' in line:
                separator_line = line
                separator_index = i
                break

        if not separator_line:
            logger.warning("未找到表格分隔线，无法重新编号")
            return test_cases_content

        # 计算列数
        column_count = separator_line.count('|')

        # 找到第一个数据行（包含编号的行）
        first_data_index = -1
        for i in range(separator_index + 1, len(lines)):
            line = lines[i]
            if line.strip().startswith('|') and line.count('|') == column_count:
                first_data_index = i
                break

        if first_data_index == -1:
            logger.warning("未找到任何数据行")
            return test_cases_content

        # 从第一个数据行中提取编号格式
        first_line = lines[first_data_index]
        parts = first_line.split('|')
        if len(parts) < 2:
            logger.warning("无法解析第一列")
            return test_cases_content

        # 获取第一列的编号（例如：IMMSG001）
        first_id = parts[1].strip()

        # 提取编号格式前缀（例如：IMMSG）
        id_match = re.match(r'^([A-Z]+)(\d+)$', first_id)
        if not id_match:
            logger.warning(f"无法识别编号格式: {first_id}")
            return test_cases_content

        prefix = id_match.group(1)  # 例如：IMMSG
        total_cases = 0

        # 重新编号所有数据行
        result_lines = lines[:first_data_index]
        i = first_data_index

        while i < len(lines):
            line = lines[i]

            # 检查是否是数据行
            if not line.strip().startswith('|'):
                # 不是表格行，添加并继续
                result_lines.append(line)
                i += 1
                continue

            # 检查列数是否正确
            if line.count('|') != column_count:
                # 列数不对，可能是空行或其他内容
                result_lines.append(line)
                i += 1
                continue

            # 这是一个数据行，重新编号
            total_cases += 1
            new_id = f"{prefix}{total_cases:03d}"  # 格式：IMMSG001

            # 替换第一列的编号，保持原有格式
            parts = line.split('|')
            if len(parts) >= 2:
                # 保持第一列（空）和第二列（编号）之间的空格
                # 只替换编号部分
                parts[1] = f" {new_id} "
                new_line = '|'.join(parts)
                result_lines.append(new_line)

            i += 1

        renumbered_content = '\n'.join(result_lines)
        logger.info(f"重新编号完成: 共{total_cases}条测试用例，编号范围: {prefix}001-{prefix}{total_cases:03d}")

        return renumbered_content
