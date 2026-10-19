# tratteggio

A small, honest RAG assistant for a fresco conservation archive.
Companion code for "The Restorer's Guide to RAG: Find, Match, Fill".

The Lanaioli Chapel, its 1460s fresco and its 15 archive records are fictional.
Standard library only; the model runs locally through Ollama.

```bash
python make_archive.py                 # write the 15 records to ./archive
python -m pytest -q tests              # 8 tests, no model needed
python -m tratteggio.eval              # retrieval scores for configurations A-D
ollama pull llama3.2
python -m tratteggio "What was the merchant holding in his right hand?"
python -m tratteggio "How big is the hole in the lower centre?" --dry-run   # retrieval and prompt only
```
