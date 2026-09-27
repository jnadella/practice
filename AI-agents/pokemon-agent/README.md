# Local Pokémon agent

A terminal chat using Ollama's llama3.2:3b and PokéAPI. No API key, signup, or pip packages required. Python 3.9+.

```sh
cd /Users/jayanthnadella/Documents/code/practice/AI-agents/pokemon-agent
python3 agent.py
```

If needed, install the model with `ollama pull llama3.2:3b` and start Ollama with its app or `ollama serve`.

Examples:
- Tell me about Pikachu.
- Compare the base speed of Pikachu and Charizard.
- Give me three Water Pokémon.
- Tell me about Bulbasaur. (Excluded by the type rules.)

Single question: `python3 agent.py --ask 'Tell me about Pikachu'`
Type `/quit` to exit chat. Edit `rules.md`; it reloads each turn.

Chat → local model chooses a tool → PokéAPI → local model gives a concise answer.
Only Fire, Water, or Electric types qualify, including dual types. Thunder means Electric. The detail tool enforces this filter in code; prompt rules guide the model's response. Language models may still make mistakes.

Tools return type membership, base stats, abilities, height and weight. Evolution and move details are not implemented. The agent does not download every Pokémon to compute global rankings; comparisons require fetched records. It can make up to 12 tool calls per question.

API responses are stored in `.cache/` to respect PokéAPI fair use and avoid repeated downloads. Cached data has no automatic expiration; remove that directory to refresh. Internet is needed for uncached data. Chats/rules remain on local Ollama; only Pokémon/type lookups go to PokéAPI. Conversation memory is the last four turns and is not saved to disk.

The complete short rules file is supplied to Ollama each turn, without an embedding database. The old car-sales project remains separate; no FRED code or key is used here.

API docs: https://pokeapi.co/docs/v2

Tests: `python3 -m unittest -v`
