import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import agent


def pokemon(types):
    return {'name': 'example', 'id': 1, 'types': [{'type': {'name': t}} for t in types],
            'stats': [{'stat': {'name': 'speed'}, 'base_stat': 90}],
            'abilities': [], 'height': 10, 'weight': 100}


class Tests(unittest.TestCase):
    def test_dual_type_allowed(self):
        with patch.object(agent, 'cached_get', return_value=pokemon(['fire', 'flying'])):
            self.assertEqual(agent.get_pokemon('example')['types'], ['fire', 'flying'])

    def test_disallowed_type_blocked(self):
        with patch.object(agent, 'cached_get', return_value=pokemon(['grass', 'poison'])):
            self.assertIn('excluded', agent.get_pokemon('example'))

    def test_thunder_alias(self):
        with patch.object(agent, 'cached_get', return_value={'pokemon': []}) as get:
            self.assertEqual(agent.list_type('thunder')['type'], 'electric')
            get.assert_called_once_with('type', 'electric')

    def test_cache_prevents_repeat_request(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(agent, 'CACHE', Path(tmp)), \
             patch.object(agent, 'request_json', return_value={'id': 25}) as get:
            self.assertEqual(agent.cached_get('pokemon', 'pikachu'), {'id': 25})
            agent.cached_get('pokemon', 'pikachu')
            get.assert_called_once()

    def test_tool_flow(self):
        replies = [{'message': {'role': 'assistant', 'content': '', 'tool_calls': [
            {'function': {'name': 'get_pokemon', 'arguments': {'name': 'pikachu'}}}]}},
            {'message': {'role': 'assistant', 'content': 'Pikachu: Electric.'}}]
        with patch.object(agent, 'request_json', side_effect=replies) as api, \
             patch.object(agent, 'cached_get', return_value=pokemon(['electric'])):
            answer = agent.answer('Pikachu?', [], 'llama3.2:3b', 'Be crisp.')
            messages = api.call_args.args[1]['messages']
            self.assertEqual(json.loads(messages[-1]['content'])['base_stats']['speed'], 90)
            self.assertIn('Pikachu', answer)


if __name__ == '__main__':
    unittest.main()
