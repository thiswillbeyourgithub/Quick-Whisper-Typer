#!/bin/zsh

# if you use a venv:
# cd YOUR_PATH
# source .venv/bin/activate

# # if you use a custom whisper, for example via speaches.ai:
# export CUSTOM_WHISPER_API_KEY="YOUR KEY"
# --custom_transcription_url="http://localhost:8001/v1/audio/transcriptions" \
#
# or to use deepgram:
# --deepgram_transcription \

python quick_whisper_typer.py  \
    --voice_engine=openai \
    --disable_voice \
    --auto_paste \
    --loop \
    --verbose \
    --sound_cleanup \
    --loop_tasks '{"n":{"task":"new_voice_chat"}, "c": {"task":"continue_voice_chat"}, "w": {"task": "write"}, "t": {"task": "transform_clipboard"}, "s": {"extra_args": "disable_voice"}, "x": {"task": "write", "LLM_instruction": "instructions/my_rules.txt"}, "d": {"task": "write", "LLM_instruction": "instructions/corrector.txt", "llm_model": "openrouter/anthropic/claude-3-5-haiku"}}'
