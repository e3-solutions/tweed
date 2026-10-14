import unittest
from unittest import mock
import bonaparte_native as native

class EventRoutingEdges(unittest.TestCase):
    def driver(self):
        value = object.__new__(native.AppServerPhaseDriver)
        value.observer = mock.Mock()
        value._receipt_thread_id = 'coordinator-root'
        value._receipt_turn_id = 'active-turn'
        value._last_agent_message = None
        return value

    def test_foreign_completion_never_establishes_current_turn_terminal(self):
        for thread,turn in [('foreign-child','active-turn'),('coordinator-root','foreign-turn'),('foreign-child','foreign-turn')]:
            with self.subTest(thread=thread,turn=turn):
                method,terminal=self.driver().observe_notification({'method':'turn/completed','params':{'threadId':thread,'turn':{'id':turn,'status':'completed'}}})
                self.assertEqual(method,'turn/completed')
                self.assertIsNone(terminal,'A foreign thread/turn completion became coordinator completion')

    def test_matching_and_legacy_completion_preserve_turn_payload(self):
        for params in [{'threadId':'coordinator-root','turn':{'id':'active-turn','status':'completed'}},{'turn':{'id':'active-turn','status':'interrupted'}}]:
            with self.subTest(params=params):
                _,terminal=self.driver().observe_notification({'method':'turn/completed','params':params})
                self.assertEqual(terminal,params['turn'])

    def test_foreign_messages_cannot_replace_coordinator_receipt(self):
        driver=self.driver()
        for thread,turn,text in [('coordinator-root','active-turn','root'),('foreign-child','active-turn','wrong-thread'),('coordinator-root','foreign-turn','wrong-turn')]:
            driver.observe_notification({'method':'item/completed','params':{'threadId':thread,'turnId':turn,'item':{'type':'agentMessage','text':text}}})
        self.assertEqual(driver._last_agent_message,'root')
