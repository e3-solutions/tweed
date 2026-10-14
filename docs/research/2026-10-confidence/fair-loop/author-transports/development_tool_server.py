"""Research/development transport facade over existing qualified WorkspaceTools."""
import importlib.util,json,pathlib,sys
config_path=pathlib.Path(sys.argv[-1]);config=json.loads(config_path.read_text())
spec=importlib.util.spec_from_file_location('development_borrowed_workspace_tools',config['borrowed_runner']);base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.NATIVE_TOOLS=('list_files','read_file','write_file','replace_text','run_tests')
base.TOOL_SCHEMAS={name:base.TOOL_SCHEMAS[name] for name in base.NATIVE_TOOLS}
original=base.WorkspaceTools.call
def bounded(self,name,args):
 if name not in base.NATIVE_TOOLS:return {'error':'Tool unavailable in this bounded development route'},{'name':name,'ok':False,'error_kind':'policy'}
 return original(self,name,args)
base.WorkspaceTools.call=bounded
base.serve(config_path)
