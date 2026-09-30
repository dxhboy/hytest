"""接口测试前后置脚本受限执行"""
from unittest import TestCase

from apps.core.pm_context import execute_pm_script


class PmScriptSandboxTest(TestCase):
    def run_script(self, script, variables=None):
        return execute_pm_script(script, variables or {})

    def test_normal_script_still_works(self):
        result = self.run_script(
            "import hashlib, json, time\n"
            "sign = hashlib.md5(('a' + str(len([1, 2]))).encode()).hexdigest()\n"
            "pm.environment.set('sign', sign)\n"
            "pm.variables.set('n', json.dumps({'k': sorted([2, 1])}))\n"
            "pm.request.headers.add('X-Ts', str(int(time.time()) > 0))\n"
            "print('ok', pm.environment.get('base'))\n",
            {'base': 'http://x'},
        )
        self.assertEqual(result['errors'], [])
        self.assertEqual(len(result['variables']['sign']), 32)
        self.assertEqual(result['variables']['n'], '{"k": [1, 2]}')
        self.assertEqual(result['extra_headers'], {'X-Ts': 'True'})
        self.assertEqual(result['console'], ['ok http://x'])

    def test_dangerous_imports_blocked(self):
        for script in ("import os\nos.system('echo hi')",
                       "import subprocess",
                       "from os import path",
                       "__import__('os')"):
            result = self.run_script(script)
            self.assertTrue(result['errors'], script)

    def test_dangerous_builtins_blocked(self):
        for script in ("open('x.txt', 'w')", "eval('1+1')", "exec('a=1')", "compile('1', 'f', 'eval')"):
            result = self.run_script(script)
            self.assertTrue(result['errors'], script)

    def test_dunder_escape_blocked(self):
        for script in ("().__class__.__base__.__subclasses__()",
                       "x = pm.__dict__",
                       "getattr(pm, '__class__')"):
            result = self.run_script(script)
            self.assertTrue(result['errors'], script)
