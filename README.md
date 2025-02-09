# Quick Whisper Typer
Super simple python script to start recording sound, send it to whisper then have it type for you anywhere.
* Can also modify text according to voice commands.
* Latency is as low as I could (instant if deepgram is used, <1s for openai's whisper).
* It can be seen as a minimalist alternative to [AquaVoice](https://withaqua.com/) and can be extended easily to replace [Deepgram's Shortcut feature](https://deepgram.com/learn/introducing-shortcut-by-poised-voice-ai-tool).t

## The way each task works
### write
1. starts recording
2. when you're done press shift (escape or spacebar to cancel)
3. whisper will transcribe your speech
4.a if `--auto_paste` is True: your current clipboard will be saved, replaced by the transcription, "ctrl+v" will automatically be pressed, then your old clipboard will replace again like nothing happened.
4.b if `--auto_paste` is False: your clipboard will be replaced by the transcription
### transform_clipboard
1. starts recording
2. when you're done press shift (escape or spacebar to cancel)
3. whisper will transcribe your speech
4. the transcription will be interpreted as an instruction for `--llm_model` on how to transform the text found in your clipboard
5. the result will either be pasted or stored in the clipboard like for `--task=write`
### new_voice_chat
1. starts recording
2. when you're done press shift (escape or spacebar to cancel)
3. whisper will transcribe your speech
4. the transcription will be interpreted as the first user message in a conversation with `--llm_model`
5. the result will either be pasted or stored in the clipboard like for `--task=write`, and optionaly read aloud if `--voice_engine` is set
6. To continue the conversation, use the task `--task=continue_voice_chat`

# Examples
* I want to write text: `python quick_whisper_typer.py --task=write --auto_paste`
* I want to translate text: copy the text in to the clipboard then `python quick_whisper_typer.py --task=transform_clipboard --auto_paste`
* I want to start a vocal conversation: `python quick_whisper_typer.py --task="new_voice_chat" --voice_engine='openai'`
* I want to continue the conversation: `python quick_whisper_typer.py --task="continue_voice_chat" --voice_engine='openai'`
* I want to call it from anywhere without setting up keybindings, use `--loop` then press `shift` key several times from anywhere and you'll see a notification appear to trigger the tasks.


## Features
* Supports any spoken languages supported by whisper
* Supports both openai's whisper and [deepgram's whisper](deepgram.com)
* Supports for local transcription by supplying a custom URL.
    * For example start [whispercpp](https://github.com/ggerganov/whisper.cpp) with `./server -m models/small_acft_q8_0.bin --threads 8 --audio-ctx 1500 -l fr --no-gpu --debug-mode --convert -p 1` ([models from FUTO](https://github.com/futo-org/whisper-acft/)) and use `--custom_transcription_url="http://127.0.0.1:8080/inference"`
    * You can set these environment variables for custom transcription:
        * `CUSTOM_WHISPER_API_KEY`: API key for the custom transcription server
        * `CUSTOM_WHISPER_MODEL`: Model name to use with the custom transcription server
* Minimalist code
* Low latency: it starts as fast as possible to be ready to listen to you
* Four supported voice_engine: openai, [piper](https://github.com/rhasspy/piper), [deepgram](deepgram.com), espeak (fallback if any of the other fails)
* Optional audio cleanup and long silence removal via sox
* `--loop` to trigger the script from anywhere just by pressing shift multiple times. You can define any king of argument to customize your loop shortcuts by passing a dict to `--loop_tasks`
* Support virtually any type of LLM (ChatGPT, Claude, Huggingface, Llama, etc) thanks to [litellm](https://docs.litellm.ai/).
* Supposedly multiplatform, but I can't test it on anything else than Linux so please open an issue to tell me how it went!

## How to
* Make sure your environment contains the appropriate api keys (eg as OPENAI_API_KEY, MISTRAL_API_KEY, DEEPGRAM_API_KEY etc)
* *optional: add a keyboard shortcut to call this script. See my i3 bindings below.*
* If using deepgram: make sure you are on python 3.10+
* `chmod +x ./quick_whisper_typer.py`
* `pip install -r requirements.txt`
    * if you have an issue installing playsound, try installing playsound3

### i3 bindings
```
mode "$mode_launch_microphone" {
    # enter text
    bindsym f exec /PATH/TO/quick_whisper_typer.py --task write, mode "default
    # edit clipboard
    bindsym e exec /PATH/TO/quick_whisper_typer.py --task=transform_clipboard, mode "default"
    bindsym v exec /PATH/TO/quick_whisper_typer.py --task=continue_voice_chat, mode "default"
    bindsym shift+V exec /PATH/TO/quick_whisper_typer.py --task=new_voice_chat, mode "default"

    bindsym Return mode "default"
    bindsym Escape mode "default"
    }
```

# Credits
* `.ogg` files were in my `/usr/share/sounds/ubuntu/notifications` folder.
