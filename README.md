# Quick Whisper Typer
Super simple python script to start recording sound, send it to whisper then have it type for you in a field. Can be used to transform the clipboard too. Latency is <2s and sometimes <1s.

## The way this works
1. Move your cursor to where you want the output to be.
2. Launch the script (preferably using a keyboard shortcut).
3. A small window pops up. If you enter text inside it will be given as instruction to ChatGPT to alter your whisper transcript. Leave empty otherwise. Press enter to close the window without moving your cursor.
4. Whisper is called on the audio.
5. If you used `--task=transform_clipboard` the output will be: ChatGPT transformation of the current clipboard according to the whisper transcript. If you didn't the output will be the whisper transcript.
6. If you entered text in the small window, it will be given as instruction to ChatGPT to further transform the output (e.g. "Translate to English")
7. The current clipboard is stored. The output text is copied. `xdotool` sends `ctrl+v` (press shift if in a console!) to add the output to where your cursor is. The clipboard is then refilled with what was previously there.

## Features
* Choose the language via `--language`
* Specify a whisper prompt in advance via `--prompt`
* If you use `--task=transform_clipboard`, then ChatGPT will be tasked to transform the content of your clipboard according to the instruction you told to whisper.
* If you use `--task=new_voice_chat` you will start a voice chat with the specified `voice_engine` used to give you back the answers. Implemented voice engines are `espeak`, `piper` and `openai`. You can continue the vocal chat indefinitely by using `task=continue_voice_chat`.
* Removes long silences via sox
* `loop.py` can be used to trigger the vocal script from any screen just by pressing shift multiple timmes.

## How to
* Put your OpenAI api key in a file called API_KEY.txt
* *optional: add a keyboard shortcut to call this script. See my i3 bindings below.*
* `chmod +x ./quick_whisper_typer.py`
* `./quick_whisper_typer.py --language en`

### i3 bindings
```
mode "$mode_launch_microphone" {
    # enter text
    bindsym f exec /PATH/TO/Quick_Whisper_Typer.py --lang en --task write, mode "default
    # edit clipboard
    bindsym e exec /PATH/TO/Quick_Whisper_Typer.py --lang en --task=transform_clipboard, mode "default"
    bindsym v exec /PATH/TO/Quick_Whisper_Typer.py --lang en --task=continue_voice_chat, mode "default"
    bindsym shift+V exec /PATH/TO/Quick_Whisper_Typer.py --lang en --task=new_voice_chat, mode "default"

    bindsym Return mode "default"
    bindsym Escape mode "default"
    bindsym $alt+pyift+r mode "default"
    }
```
