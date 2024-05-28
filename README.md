# Quick Whisper Typer
Super simple python script to start recording sound, send it to whisper then have it type for you anywhere.
* Can also modify text according to voice commands.
* Latency is as low as I could (<1s before starting to speak).
* It can be seen as a minimalist alternative to [AquaVoice](https://withaqua.com/)

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
* Minimalist code
* Low latency: it starts as fast as possible to be ready to listen to you
* Multiple voice_engine: openai, [piper](https://github.com/rhasspy/piper), espeak (fallback if any of the other two fails)
* Optional audio cleanup and long silence removal via sox
* `--loop` to trigger the script from anywhere just by pressing shift multiple times. You can define any king of argument to customize your loop shortcuts by passing a dict to `--loop_tasks`
* Support virtually any type of LLM (ChatGPT, Claude, Huggingface, Llama, etc) thanks to [litellm](https://docs.litellm.ai/).
* Supposedly multiplatform, but I can't test it on anything else than Linux so please open an issue to tell me how it went!

## How to
* Put your OpenAI api key in a file called OPENAI_API_KEY.txt.
* *optional: add a keyboard shortcut to call this script. See my i3 bindings below.*
* `chmod +x ./quick_whisper_typer.py`

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
