"""Offline fabricated raw-event controls, never model outcomes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import controller as c
import discovery as d

class DiscoveryControls(unittest.TestCase):
    def receipt(self,root):
        source=root/'base';source.mkdir();(source/'toy.py').write_text('VALUE = 1\n')
        task={'task_id':'toy','prompt':'Set VALUE=2','base_snapshot':str(source),'production_paths':['toy.py']}
        packet=d.packet(task);out=root/'discovery';out.mkdir()
        facts=[{'path':'toy.py','start_line':1,'end_line':1,'quote':'VALUE = 1','fact':'untrusted interpretation never shared'}]
        events=[{'type':'system','subtype':'init','tools':['StructuredOutput'],'mcp_servers':[]},{'type':'assistant','message':{'model':d.MODEL,'content':[]}},{'type':'result','subtype':'success','is_error':False,'structured_output':{'facts':facts}}]
        c.write(out/'packet.json',packet);c.write(out/'request.json',{'argv':d.request_argv(packet),'model_requested':d.MODEL,'effort':'medium','timeout_seconds':120,'budget_usd':.6})
        (out/'stream.stdout').write_text(''.join(json.dumps(event)+'\n' for event in events));(out/'stream.stderr').write_text('')
        stage={**d.parse_events(events),'model_requested':d.MODEL,'timed_out':False,'process_exit':0,'process_cleanup_scope':'original_process_group','detached_descendants_contained':False,'stdout_sha256':c.sha(out/'stream.stdout'),'stderr_sha256':c.sha(out/'stream.stderr')}
        receipt={'artifact_root':str(out),'artifact_files':{name:c.sha(out/name) for name in ('packet.json','request.json','stream.stdout','stream.stderr')},'packet_sha256':c.digest(packet),'stage':stage,'validated_facts':facts}
        return task,receipt,out
    def test_quote_lines_raw_model_and_no_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            task,receipt,out=self.receipt(Path(temp));self.assertTrue(d.validate_receipt(receipt,task))
            receipt['validated_facts'][0]['quote']='VALUE = 2'
            with self.assertRaises(ValueError):d.validate_receipt(receipt,task)
    def test_raw_stream_missing_or_changed_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            task,receipt,out=self.receipt(Path(temp));(out/'stream.stdout').write_text('')
            with self.assertRaises(ValueError):d.validate_receipt(receipt,task)
    def test_forged_observed_model_not_promoted(self):
        with tempfile.TemporaryDirectory() as temp:
            task,receipt,out=self.receipt(Path(temp));receipt['stage']['observed_assistant_models']=['wrong']
            with self.assertRaises(ValueError):d.validate_receipt(receipt,task)

if __name__=='__main__':unittest.main()
