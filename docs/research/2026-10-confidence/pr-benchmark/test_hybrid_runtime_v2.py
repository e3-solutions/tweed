"""Actual executable callback/confinement controls; no hosted inference."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('runtime_v2_test_controller', HERE/'hybrid_v2.py')
controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
runtime_spec = importlib.util.spec_from_file_location('runtime_v2_tests', HERE/'hybrid_runtime_v2.py')
runtime = importlib.util.module_from_spec(runtime_spec); runtime_spec.loader.exec_module(runtime)
runtime.install(controller.frozen.base, controller.frozen.backend)


@unittest.skipUnless(Path('/usr/bin/sandbox-exec').exists(), 'Requires macOS sandbox')
class ExecutableRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.actor = self.root/'workspace'; self.actor.mkdir()
        (self.actor/'product.py').write_text('answer=2\n')
        (self.actor/'.trial-tmp').mkdir()
        self.base = controller.frozen.base

    def tearDown(self): self.temp.cleanup()

    def command(self, code, stage='main', readonly=False):
        control = self.root/stage; control.mkdir(exist_ok=True)
        deadline = time.time()+20
        worker = self.base.WorkspaceTools(dict(workspace=str(self.actor), control=str(control),
            temporary=str(self.actor/'.trial-tmp'), readonly=readonly, deadline=deadline,
            python_executable=__import__('sys').executable))
        box = {}
        thread = threading.Thread(target=lambda: box.update(value=worker.call('run_tests', {'argv':['python3','-B','-c',code]})))
        thread.start()
        while thread.is_alive() and time.time()<deadline:
            self.base.service_commands(control,self.actor,self.actor/'.trial-tmp',readonly,deadline)
            time.sleep(.01)
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive(),'Actual command callback failed to respond')
        result, event = box['value']
        self.assertTrue(event['ok'], result)
        return result

    def test_blank_child_home_outside_checkout_no_inherited_auth(self):
        code = 'import json,os,pathlib,tempfile; print(json.dumps(dict(home=str(pathlib.Path.home()),tmp=tempfile.gettempdir(),auth=os.getenv("FAKE_RUNTIME_AUTH"),files=list(pathlib.Path.home().iterdir())),default=str))'
        with patch.dict(__import__('os').environ, {'FAKE_RUNTIME_AUTH':'SYNTHETIC_NOT_A_SECRET'}):
            result = self.command(code)
        self.assertEqual(result['exit_code'],0)
        value=json.loads(result['output'])
        self.assertIsNone(value['auth']); self.assertEqual(value['files'],[])
        self.assertEqual(Path(value['home']),self.root/'main/execution-scratch/home')
        self.assertFalse(Path(value['tmp']).is_relative_to(self.actor))

    def test_copying_repository_into_temp_does_not_copy_its_own_destination(self):
        result=self.command('import pathlib,shutil,tempfile; d=pathlib.Path(tempfile.mkdtemp())/"copy"; shutil.copytree(pathlib.Path.cwd(),d); assert (d/"product.py").read_text()=="answer=2\\n"; print("COPY_PASS")')
        self.assertEqual(result['exit_code'],0,result.get('error_output')); self.assertIn('COPY_PASS',result['output'])

    def test_readonly_source_and_controller_response_write_denied_scratch_write_allowed(self):
        target=self.root/'peer/secret-response.json'; target.parent.mkdir(); target.write_text('DO_NOT_CHANGE')
        code='import pathlib; p=pathlib.Path; denied=[]\nfor target in [p("product.py"),p('+repr(str(target))+')]:\n try: target.write_text("FORBIDDEN")\n except PermissionError: denied.append(True)\nassert len(denied)==2; (p.home()/"allowed").write_text("ok"); print("READONLY_PASS")'
        result=self.command(code,stage='peer',readonly=True)
        self.assertEqual(result['exit_code'],0,result.get('error_output'))
        self.assertEqual((self.actor/'product.py').read_text(),'answer=2\n'); self.assertEqual(target.read_text(),'DO_NOT_CHANGE')

    def test_cross_stage_scratch_and_outside_private_file_reads_denied(self):
        first=self.command('import pathlib; (pathlib.Path.home()/"first").write_text("FIRST_STAGE"); print("created")',stage='first')
        self.assertEqual(first['exit_code'],0)
        outside=self.root/'private'; outside.write_text('SYNTHETIC_PRIVATE_SENTINEL')
        prior=self.root/'first/execution-scratch/home/first'
        code='import pathlib; denied=[]\nfor target in ['+repr(str(prior))+','+repr(str(outside))+']:\n try: pathlib.Path(target).read_text()\n except PermissionError: denied.append(True)\nassert len(denied)==2; print("ISOLATION_PASS")'
        result=self.command(code,stage='second')
        self.assertEqual(result['exit_code'],0,result.get('error_output'))

    def test_scratch_and_home_symlinks_refused_before_execution(self):
        for which in ('scratch','home'):
            control=self.root/which; control.mkdir()
            scratch=control/'execution-scratch'
            if which=='scratch': scratch.symlink_to(self.actor,target_is_directory=True)
            else:
                scratch.mkdir(); (scratch/'home').symlink_to(self.actor,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'symlink'):
                self.base.service_commands(control,self.actor,self.actor/'.trial-tmp',False,time.time()+10)


if __name__=='__main__': unittest.main()
