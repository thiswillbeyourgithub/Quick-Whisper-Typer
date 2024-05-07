import os
from pathlib import Path
import tempfile
import subprocess
import time



class QuickWhisper:
    system_prompts = {
        "voice": "You are a helpful assistant. I am in a hurry and your "
            "answers will be played on speaker so use as few words as you "
            "can while remaining helpful and truthful. Don't use too short "
            "sentences otherwise the speakers will crash.",
        "transform_clipboard": "You transform INPUT_TEXT according to an "
            "instruction. Only reply the transformed text without anything else.",
    }
    allowed_tasks = (
        "transform_clipboard",
        "new_voice_chat",
        "continue_voice_chat",
        "write",
        "custom",
    )
    allowed_voice_engine = ("openai", "piper", "espeak", None)

    # arguments to do voice cleanup before sending to whisper
    sox_cleanup = [
        # isolate voice frequency
        # -2 is for a steeper filtering
        ["highpass", "-1", "100"],
        ["lowpass", "-1", "3000"],
        # removes high frequency and very low ones
        ["highpass", "-2", "50"],
        ["lowpass", "-2", "5000"],
        # # normalize audio
        ["norm"],
        # max silence should be 1s
        ["silence", "-l", "1", "0", "0.5%", "-1", "1.0", "0.1%"],
        # # remove leading silence
        # ["vad", "-p", "0.2", "-t", "5"],
        # # # and ending silence, this might be unecessary for splitted audio
        # ["reverse"],
        # ["vad", "-p", "0.2", "-t", "5"],
        # ["reverse"],
        # add blank sound to help whisper
        ["pad", "0.2@0"],
    ]

    def __init__(
        self,
        task=None,
        model="openai/gpt-3.5-turbo-0125",
        auto_paste=False,
        sound_cleanup=False,
        whisper_prompt=None,
        whisper_lang=None,
        voice_engine=None,
        piper_model_path=None,
        LLM_instruction=None,
        gui=False,
        daemon_mode=False,
    ):
        """
        Parameters
        ----------
        task
            transform_clipboard, write, voice_chat

        model: str, default "openai/gpt-3.5-turbo-0125"

        auto_paste, default False
            if True, will use xdotool to paste directly. Otherwise just plays
            a sound to tell you that the clipboard was filled.

        sound_cleanup: bool, default False
            Clean up the sound before sending it to whisper, but this adds
            latency depending of how powerful your computer is.
            This uses sox, to modify the arguments, look at the value
            of self.sox_cleanup

        whisper_prompt: str, default None
            prompt to given to whisper

        whisper_lang: str, default None

        voice_engine, default None
            piper, openai, espeak, None

        piper_model_path: str, default None
            name of a piper model file.
            For example 'en_US-lessac-medium'. Make sure you have 
            a .onxx and .json file present.
            More info: https://github.com/rhasspy/piper

        LLM_instruction: str, default None
            if given, then the transcript will be given to an LLM and tasked
            to modify it according to those instructions. Meaning this is
            the system prompt.

        gui, default to False
            if True, a window will open to allow to enter specific prompts etc
            if False, no window is used and you have to press shift to stop the recording.

        daemon_mode
            default to False. Designed for loop.py Is either False or a queue
            that stops listening when an item is received.
            if True, gui argument is ignored
        """
        if not task:
            raise Exception(f"You must specify a task from {self.allowed_tasks}")
        if gui is True:
            assert (
                not whisper_prompt
            ), "whisper_prompt already given, shouldn't launch gui"
            assert (
                not LLM_instruction
            ), "LLM_instruction already given, shouldn't launch gui"

        if gui or LLM_instruction:
            assert "/" in model, f"LLM model name must be given in litellm format"

        # Checking voice engine
        if voice_engine == "None":
            voice_engine = None
        assert (
            "voice" not in task or voice_engine in self.allowed_voice_engine
        ), f"Invalid voice engine {voice_engine} not part of {self.allowed_voice_engine}"
        if voice_engine == "piper":
            assert piper_model_path, "To use piper as a voice engine you must supply a piper_model_path value"
            if not Path(piper_model_path).exists():
                raise Exception(f"FileNotFound for pipermodelpath: {piper_model_path}")

        # Checking that the task is allowed
        task = task.replace("-", "_").lower()
        assert (
            task != "" and task in self.allowed_tasks
        ), f"Invalid task {task} not part of {self.allowed_tasks}"

        self.log(f"Will use prompt {whisper_prompt} and task {task}")

        file = tempfile.NamedTemporaryFile(suffix=".mp3").name
        min_duration = 2  # if the recording is shorter, exit

        # Kill any previously running recordings
        start_time = time.time()
        subprocess.run(
            ["killall", "rec"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        # Start recording
        self.log(f"Recording {file}")
        subprocess.Popen(f"rec -r 44000 -c 1 -b 16 {file} &", shell=True)
        from playsound import playsound

        self.notif("Listening")
        playsound("sounds/Slick.ogg")

        if daemon_mode is not False:
            if daemon_mode.get() == "STOP":
                raise NotImplementedError()
        elif gui is True:
            # Show recording form
            whisper_prompt, LLM_instruction = self.popup(
                whisper_prompt,
                task,
                )
        else:
            from pynput import keyboard

            def released_shift(key):
                if key == keyboard.Key.shift:
                    self.log("Pressed shift.")
                    time.sleep(1)
                    return False
                elif key in [keyboard.Key.esc, keyboard.Key.space]:
                    self.notif(self.log("Pressed escape or spacebar: quitting."))
                    os.system("killall rec")
                    raise SystemExit("Quitting.")

            with keyboard.Listener(on_release=released_shift) as listener:
                self.log("Shortcut listener started, press shift to stop recodring, esc or spacebar to quit.")

                # import last minute to be quicker to launch
                if sound_cleanup:
                    import soundfile as sf
                    import torchaudio

                from litellm import completion, transcription

                for path in list(Path(".").rglob("./*API_KEY.txt")):
                    backend = path.name.split("_API_KEY.txt")[0]
                    content = path.read_text().strip()
                    os.environ[f"{backend.upper()}_API_KEY"] = content

                listener.join()  # blocking

        # Kill the recording
        subprocess.run(
            ["killall", "rec"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        end_time = time.time()
        self.log(f"Done recording {file}")
        playsound("sounds/Rhodes.ogg")
        if gui is False:
            self.notif("Analysing")

        # Check duration
        duration = end_time - start_time
        self.log(f"Duration {duration}")
        if duration < min_duration:
            self.notif(
                self.log(
                    f"Recording too short ({duration} s), exiting without calling whisper."
                )
            )
            raise SystemExit()

        if sound_cleanup:
            # clean up the sound
            self.log("Cleaning up sound")

            try:
                waveform, sample_rate = torchaudio.load(file)
                waveform, sample_rate = torchaudio.sox_effects.apply_effects_tensor(
                    waveform,
                    sample_rate,
                    self.sox_cleanup,
                )
                file2 = file.replace(".mp3", "") + "_clean.wav"
                sf.write(str(file2), waveform.numpy().T,
                         sample_rate, format="wav")
                file = file2
                self.log("Done cleaning up sound")
            except Exception as err:
                self.log(f"Error when cleaning up sound: {err}")

        # Call whisper
        self.log("Calling whisper")
        with open(file, "rb") as f:
            transcript_response = transcription(
                model="whisper-1",
                file=f,
                language=whisper_lang,
                prompt=whisper_prompt,
                temperature=0,
            )
        text = transcript_response.text
        self.notif(self.log(f"Transcript: {text}"))

        import pyclip

        if task == "write":
            try:
                clipboard = pyclip.paste()
            except Exception as err:
                self.log(f"Erasing the previous clipboard because error when loding it: {err}")
                clipboard = ""

            if LLM_instruction:
                self.log(
                    f"Calling {model} to transfrom the transcript to follow "
                    f"those instructions: {LLM_instruction}"
                )
                messages=[
                    {
                        "role": "system",
                        "content": LLM_instruction,
                    },
                    {
                        "role": "user",
                        "content": text,
                    },
                ]
                import json
                self.log(f"Messages sent to LLM:\n{json.dumps(messages, indent=4, ensure_ascii=False)}")

                LLM_response = completion(
                    model=model,
                    messages=messages,
                )
                answer = LLM_response.json(
                )["choices"][0]["message"]["content"]
                self.log(f'LLM output: "{answer}"')
                text = answer

            self.log("Pasting clipboard")
            # pyautogui.click()
            pyclip.copy(text)
            if auto_paste:
                os.system("xdotool key ctrl+v")
                pyclip.copy(clipboard)
                self.log("Clipboard reset")

            self.notif("Done")
            playsound("sounds/Positive.ogg")

        elif task == "transform_clipboard":
            self.log(
                f'Calling LLM with instruction "{text}" and tasked to transform the clipboard'
            )

            try:
                clipboard = str(pyclip.paste())
            except Exception as err:
                raise Exception(
                        f"Error when loading content of clipboard: {err}")

            if not clipboard:
                self.notif(self.log("Clipboard is empty, this is not compatible with the task"))
                raise SystemExit()
            if isinstance(clipboard, str):
                self.log(f"Clipboard previous content: '{clipboard}'")
            elif isinstance(clipboard, bytes):
                self.log(f"Clipboard previous content is binary")

            assert len(clipboard) < 10000, f"Suspiciously large clipboard content: {len(clipboard)}"
            assert len(text) < 10000, f"Suspiciously large text content: {len(text)}"
            LLM_response = completion(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": self.system_prompts["transform_clipboard"],
                    },
                    {
                        "role": "user",
                        "content": f"INPUT_TEXT: '{clipboard}'\n\nINSTRUCTION: '{text}'",
                    },
                ],
            )
            answer = LLM_response.json()["choices"][0]["message"]["content"]
            self.log(f'LLM clipboard transformation: "{answer}"')

            self.log("Pasting clipboard")
            # pyautogui.click()
            pyclip.copy(answer)
            self.notif(answer)
            if auto_paste:
                os.system("xdotool key ctrl+v")
                pyclip.copy(clipboard)
                self.log("Clipboard reset")

            playsound("sounds/Positive.ogg")

        elif "voice_chat" in task:
            if "new" in task:
                voice_file = f"/tmp/quick_whisper_chat_{int(time.time())}.txt"
                self.log(f"Creating new voice chat file: {voice_file}")

                messages = [
                    {"role": "system", "content": self.system_prompts["voice"]},
                ]

            elif "continue" in task:
                voice_files = [
                    f
                    for f in Path("/tmp").iterdir()
                    if f.name.startswith("quick_whisper_chat_")
                ]
                voice_files = sorted(
                    voice_files, key=lambda x: x.stat().st_ctime)
                voice_file = voice_files[-1]

                self.log(f"Reusing previous voice chat file: {voice_file}")

                with open(voice_file, "r") as f:
                    lines = [line.strip() for line in f.readlines()]

                messages = [
                    {"role": "system", "content": self.system_prompts["voice"]}]
                role = "assistant"
                for line in lines:
                    if not line:
                        continue
                    if line == "#####":
                        role = "user" if role == "assistant" else "assistant"
                    else:
                        if role == messages[-1]["role"]:
                            messages[-1]["content"] += "\n" + line
                        else:
                            messages.append({"role": role, "content": line})
            else:
                raise ValueError(task)

            messages.append({"role": "user", "content": text})

            self.log(f"Calling LLM with messages: '{messages}'")
            LLM_response = completion(model=model, messages=messages)
            answer = LLM_response.json()["choices"][0]["message"]["content"]
            self.log(f'LLM answer to the chat: "{answer}"')
            self.notif(answer)

            vocal_file_mp3 = tempfile.NamedTemporaryFile(suffix=".mp3").name
            if voice_engine == "piper":
                try:
                    from piper.voice import PiperVoice as piper
                    import wave
                    voice = piper.load(piper_model_path)

                    self.log(f"Synthesizing speech to {vocal_file_mp3}")
                    with wave.open(vocal_file_mp3, "wb") as wav_file:
                        voice.synthesize(answer, wav_file)

                    self.log(f"Playing voice file: {vocal_file_mp3}")
                    playsound(vocal_file_mp3)
                except Exception as err:
                    self.notif(
                        self.log(f"Error with piper, trying with espeak: '{err}'"))
                    voice_engine = "espeak"

            if voice_engine == "openai":
                try:
                    from openai import OpenAI
                    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
                    response = client.audio.speech.create(
                        model="tts-1",
                        voice="echo",
                        input=answer,
                        response_format="mp3",
                        speed=1,
                    )
                    response.stream_to_file(vocal_file_mp3)
                    playsound(vocal_file_mp3)
                except Exception as err:
                    self.notif(
                        self.log(f"Error with openai voice_engine, trying with espeak: '{err}'"))
                    voice_engine = "espeak"

            if voice_engine == "espeak":
                subprocess.run(
                    ["espeak", "-v", whisper_lang, "-p", "20", "-s", "110", "-z", answer]
                )

            if voice_engine is None:
                self.log("voice_engine is None: not speaking.")

            # Add text and answer to the file
            with open(voice_file, "a") as f:
                f.write("\n#####\n")
                f.write(f"{text}\n")
                f.write("\n#####\n")
                f.write(f"{answer}\n")

        self.log("Done.")

    @classmethod
    def log(self, message):
        print(message)
        with open("texts.log", "a") as f:
            f.write(f"{int(time.time())} {message}\n")
        return message


    @classmethod
    def notif(self, message):
        from plyer import notification

        notification.notify(title="Quick Whisper", message=message, timeout=-1)


    def popup(self, prompt, task):
        import PySimpleGUI as sg

        title = "Sound Recorder"

        layout = [
            [sg.Text(f"TASK: {task}")],
            [sg.Text("Whisper prompt"), sg.Input(prompt)],
            [sg.Text("LLM instruction"), sg.Input()],
            [
                sg.Button("Cancel", key="-CANCEL-", button_color="blue"),
                sg.Button("Go!", key="-GO-", button_color="red"),
            ],
        ]

        window = sg.Window(title, layout, keep_on_top=True)
        event, values = window.read()
        window.close()

        if event == "-GO-":
            whisper_prompt = values[0]
            LLM_instruction = values[1]
            self.log(f"Whisper prompt: {whisper_prompt} for task {task}")
            return whisper_prompt, LLM_instruction
        else:
            self.log("Pressed cancel or escape. Exiting.")
            subprocess.run(
                ["killall", "rec"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            raise SystemExit()



if __name__ == "__main__":
    import fire
    args, kwargs = fire.Fire(lambda *args, **kwargs: [args, kwargs])
    if "help" in kwargs:
        print(help(QuickWhisper))
        raise SystemExit()
    try:
        QuickWhisper(*args, **kwargs)
    except Exception as err:
        os.system("killall rec")
        QuickWhisper.notif(f"Error: {err}")
        raise
