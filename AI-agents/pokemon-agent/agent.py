#!/usr/bin/env python3
"""Local Ollama chat with cached PokéAPI tools. No keys or pip dependencies."""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / '.cache'
API = 'https://pokeapi.co/api/v2'
OLLAMA = 'http://localhost:11434/api'
ALLOWED = {'fire', 'water', 'electric'}
ALIASES = {'thunder': 'electric', 'electricity': 'electric', 'lightning': 'electric'}


def request_json(url, payload=None, timeout=30):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=data, headers={'Content-Type': 'application/json',
                                         'User-Agent': 'LocalPokemonPracticeAgent/1.0'})
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f'HTTP {exc.code}: resource unavailable. Check the name/model and retry.') from None
    except (URLError, OSError, TimeoutError):
        raise RuntimeError('Connection failed or timed out. Check internet access and Ollama.') from None
    except ValueError:
        raise RuntimeError('Server returned invalid JSON.') from None


def cached_get(resource, name):
    # Only fixed resources and safe slugs can produce external requests.
    if resource not in {'pokemon', 'type'} or not re.fullmatch(r'[a-z0-9-]+', name):
        raise ValueError('Use a Pokémon name/ID or a valid type.')
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f'{resource}-{name}.json'
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (ValueError, OSError):
            pass
    data = request_json(f'{API}/{resource}/{name}/')
    path.write_text(json.dumps(data))
    return data


def list_type(type_name):
    name = str(type_name).lower().strip()
    name = ALIASES.get(name, name)
    if name not in ALLOWED:
        return {'error': 'Only Fire, Water, and Electric Pokémon are allowed.'}
    data = cached_get('type', name)
    return {'type': name, 'names': [p['pokemon']['name'] for p in data['pokemon']],
            'source': f'{API}/type/{name}/',
            'note': 'Complete names from this type endpoint; no stats fetched yet.'}


def get_pokemon(name):
    name = str(name).lower().strip().replace(' ', '-')
    data = cached_get('pokemon', name)
    types = [t['type']['name'] for t in data['types']]
    if not ALLOWED.intersection(types):
        return {'excluded': name, 'reason': 'Not a Fire, Water, or Electric Pokémon.'}
    return {'name': data['name'], 'id': data['id'], 'types': types,
            'base_stats': {s['stat']['name']: s['base_stat'] for s in data['stats']},
            'abilities': [a['ability']['name'] for a in data['abilities']],
            'height_m': data['height'] / 10, 'weight_kg': data['weight'] / 10,
            'source': f"{API}/pokemon/{data['name']}/"}


TOOLS = [
    {'type': 'function', 'function': {
        'name': 'list_type', 'description': 'List all names of Fire, Water, or Electric Pokémon. Thunder means Electric. Does not return stats.',
        'parameters': {'type': 'object', 'properties': {'type_name': {'type': 'string'}},
                       'required': ['type_name']}}},
    {'type': 'function', 'function': {
        'name': 'get_pokemon', 'description': 'Get verified types, base stats, abilities, height and weight for one Pokémon name or ID. Other types are excluded.',
        'parameters': {'type': 'object', 'properties': {'name': {'type': 'string'}},
                       'required': ['name']}}},
]


def execute_tool(call):
    function = call.get('function', {})
    name, args = function.get('name'), function.get('arguments', {})
    if isinstance(args, str):
        args = json.loads(args)
    if not isinstance(args, dict):
        raise ValueError('Invalid tool arguments.')
    if name == 'list_type':
        return list_type(args['type_name'])
    if name == 'get_pokemon':
        return get_pokemon(args['name'])
    return {'error': 'Unknown tool; use list_type or get_pokemon.'}


def load_rules(path):
    text = path.read_text(encoding='utf-8').strip()
    if not text or len(text) > 12000:
        raise RuntimeError('Rules must contain 1–12,000 characters.')
    return text


def answer(question, history, model, rules):
    messages = [{'role': 'system', 'content': rules}] + history[-8:] + [
        {'role': 'user', 'content': question}]
    # Bound API work and tool loops. Each resource is cached after its first fetch.
    calls_left = 12
    sources = set()
    for round_index in range(5):
        payload = {'model': model, 'messages': messages, 'stream': False,
                   'options': {'temperature': 0, 'num_ctx': 16384, 'num_predict': 500}}
        if round_index < 4 and calls_left:
            payload['tools'] = TOOLS
        else:
            messages.append({'role': 'system', 'content': 'Tool budget reached. Answer only from retrieved evidence. State limits; never claim exhaustive ranking from a sample.'})
        response = request_json(OLLAMA + '/chat', payload, timeout=180)
        msg = response.get('message', {})
        calls = msg.get('tool_calls', [])
        if not calls:
            content = msg.get('content', '').strip()
            if not content:
                raise RuntimeError('Ollama returned an empty answer. Try a simpler question.')
            if sources:
                content += '\nSource: PokéAPI (' + ', '.join(sorted(sources)) + ')'
            return content
        messages.append(msg)
        for call in calls:
            if calls_left <= 0:
                result = {'error': 'Tool budget reached; answer using evidence already fetched.'}
            else:
                calls_left -= 1
                try:
                    result = execute_tool(call)
                except (RuntimeError, ValueError, KeyError, TypeError) as exc:
                    result = {'error': str(exc)}
            if result.get('source'):
                sources.add(result['source'])
            messages.append({'role': 'tool', 'tool_name': call.get('function', {}).get('name', ''),
                             'content': json.dumps(result)})
    raise RuntimeError('Model did not finish within the tool budget. Try a more specific question.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='llama3.2:3b')
    parser.add_argument('--rules', type=Path, default=ROOT / 'rules.md')
    parser.add_argument('--ask', help='Ask one question and exit.')
    args = parser.parse_args()
    load_rules(args.rules)
    models = request_json(OLLAMA + '/tags').get('models', [])
    if args.model not in {m.get('name') for m in models}:
        raise RuntimeError(f'Install the model first: ollama pull {args.model}')
    if args.ask:
        print(answer(args.ask, [], args.model, load_rules(args.rules)))
        return
    print('Pokémon chat • Fire / Water / Electric • /quit to exit')
    history = []
    while True:
        try:
            question = input('\nYou: ').strip()
        except EOFError:
            break
        if question.lower() in {'/quit', '/exit'}:
            break
        if not question:
            continue
        if len(question) > 2000:
            print('Please keep questions under 2,000 characters.')
            continue
        try:
            result = answer(question, history, args.model, load_rules(args.rules))
            print('\nAgent: ' + result)
            history += [{'role': 'user', 'content': question},
                        {'role': 'assistant', 'content': result}]
            history = history[-8:]
        except (RuntimeError, OSError) as exc:
            print('Error:', exc)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError) as exc:
        print('Error:', exc, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nGoodbye.')
