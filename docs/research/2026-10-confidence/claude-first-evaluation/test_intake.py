import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import intake

class ReadinessTest(unittest.TestCase):
 def payload(self):return {'cases':[intake.CASES[0]],'policies':{'baseline':{}}}
 def spec(self):return {'case':'resume-precedence','policy':'baseline','repeat':1}
 def questions(self):return ['Does explicit numeric on resume override saved?', 'If omitted on resume should saved checkpoint preserve?', 'Does environment override saved checkpoint on resume?']
 def test_question_recognition_is_not_received_user_authority(self):
  response={'eligible':True,'value':{'questions':self.questions(),'settled':[],'ready':True,'missing':[]}}
  with tempfile.TemporaryDirectory() as td,patch.object(intake,'call',return_value=response):
   result=intake.episode(self.spec(),self.payload(),Path(td)/'episode')
  self.assertTrue(result['premature_ready'])
  self.assertEqual(result['answered_before_terminal'],[])
  self.assertEqual(len(result['covered_decisions']),3)
 def test_final_reply_can_incorporate_answers_from_previous_round(self):
  responses=[{'eligible':True,'value':{'questions':self.questions(),'settled':[],'ready':False,'missing':['user decisions']}}, {'eligible':True,'value':{'questions':[],'settled':[d['answer'] for d in intake.CASES[0]['decisions']],'ready':True,'missing':[]}}]
  with tempfile.TemporaryDirectory() as td,patch.object(intake,'call',side_effect=responses):
   result=intake.episode(self.spec(),self.payload(),Path(td)/'episode')
  self.assertFalse(result['premature_ready'])
  self.assertEqual(len(result['answered_before_terminal']),3)
  self.assertEqual(result['rounds'],2)
 def test_unrecognized_question_does_not_resolve_missing_decisions(self):
  response={'eligible':True,'value':{'questions':['What editor should I use?'],'settled':[],'ready':False,'missing':['unknown choices']}}
  with tempfile.TemporaryDirectory() as td,patch.object(intake,'call',return_value=response):
   result=intake.episode(self.spec(),self.payload(),Path(td)/'episode')
  self.assertEqual(result['covered_decisions'],[])
  self.assertEqual(result['rounds'],3)
if __name__=='__main__':unittest.main()
