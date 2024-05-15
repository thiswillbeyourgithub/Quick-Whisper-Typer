from typing import List
import threading
import queue
from pathlib import Path
import time

DEBUG_IMPORT = False


class QuickWhisper:
    system_prompts = {
        "voice": "You are a helpful assistant. I am in a hurry and your "
            "answers will be played on speaker so use as few words as you "
            "can while remaining helpful and truthful. Don't use too short "
            "sentences otherwise the speakers will crash.",
        "transform_clipboard": "You transform INPUT_TEXT according to an "
            "instruction. Only reply the transformed text without anything "
            "else. No extra formatting, don't wraps in quotes etc",
    }
    allowed_tasks = (
        "transform_clipboard",
        "new_voice_chat",
        "continue_voice_chat",
        "write",
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
        task: str = None,
        llm_model: str = "openai/gpt-4o",
        auto_paste: bool = False,
        sound_cleanup: bool = False,
        whisper_prompt: str = None,
        whisper_lang: str = None,
        voice_engine: str = None,
        piper_model_path: str = None,
        LLM_instruction: str = None,
        gui: bool = False,
        loop: bool = False,
        loop_shift_nb: int = 3,
        loop_time_window: int = 2,
        verbose: bool = False,
        disable_bells: bool = False,
        disable_notifications: bool = False,
    ):
        """
        Parameters
        ----------
        task
            transform_clipboard, write, new_voice_chat, continue_voice_chat
            or None if --loop

        llm_model: str, default "openai/gpt-4o
            language model to use for the task except if task==write

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

        loop: bool, default False
            if True, will run an endless loop. If you press the shift key
            loop_shift_nb times you can call quick_whisper from anywhere.

        loop_shift_nb: int, default 3
            number of  times you have to press shift for the loop to trigger

        loop_time_window: int, default 2
            every that much time, the number of shift counted will be reset
            (rolling window)

        verbose: bool, default False

        disable_bells: bool, default False
            disable sound feedback

        disable_notifications: bool, default False
            disable notifications, except for the loop trigger
        """
        # store arguments
        self.verbose = verbose
        self.gui = gui
        self.llm_model = llm_model
        self.voice_engine = voice_engine
        self.piper_model_path = piper_model_path
        self.auto_paste = auto_paste
        self.sound_cleanup = sound_cleanup
        self.LLM_instruction = LLM_instruction
        self.whisper_lang = whisper_lang
        self.whisper_prompt = whisper_prompt
        self.disable_notifications = disable_notifications
        self.disable_bells = disable_bells
        self.disable_voice = False  # toggle via loop

        if verbose:
            global DEBUG_IMPORT
            DEBUG_IMPORT = True

        # check arguments
        if gui is True:
            assert (
                not whisper_prompt
            ), "whisper_prompt already given, shouldn't launch gui"
            assert (
                not LLM_instruction
            ), "LLM_instruction already given, shouldn't launch gui"

        if gui or LLM_instruction:
            assert "/" in llm_model, f"LLM model name must be given in litellm format"
        if voice_engine == "None":
            voice_engine = None
        if task is None:
            task = ""
        assert (
            "voice" not in task or voice_engine in self.allowed_voice_engine
        ), f"Invalid voice engine {voice_engine} not part of {self.allowed_voice_engine}"
        if voice_engine == "piper":
            assert piper_model_path, "To use piper as a voice engine you must supply a piper_model_path value"
            if not Path(piper_model_path).exists():
                raise Exception(f"FileNotFound for pipermodelpath: {piper_model_path}")
        task = task.replace("-", "_").lower()
        assert (
            loop or task in self.allowed_tasks
        ), f"Invalid task {task} not part of {self.allowed_tasks}"
        if loop:
                assert not task, "If using loop, you must leave task to None"

        # to reduce startup time, use threaded module import
        to_import = [
            "from playsound import playsound as playsound",
            "from plyer import notification as notification",
            "import tempfile",
            "import subprocess"
        ]
        if gui:
            to_import.append("import PySimpleGUI as sg")
        else:
            to_import.append("from pynput import keyboard")
        to_import.append("import os")
        if sound_cleanup:
            to_import.append("import torchaudio")
            to_import.append("import soundfile as sf")
        to_import.append("from litellm import completion, transcription")
        if loop or task == "write":
            to_import.append("import json")
        if loop or task == "write" or task == "transform_clipboard":
            to_import.append("import pyclip")
        if loop or "voice" in task:
            if voice_engine:
                if voice_engine == "piper":
                    to_import.append("from piper.voice import PiperVoice as piper")
                    to_import.append("import wave")
                    if piper_model_path:
                        to_import.append(f"voice = piper.load('{piper_model_path}')")
                elif voice_engine == "openai":
                    to_import.append("from openai import OpenAI")

        self.import_thread = threading.Thread(target=importer, args=(to_import,))
        self.import_thread.start()

        if loop:
            # the module were imported already
            self.loop_shift_nb = loop_shift_nb
            self.loop_time_window = loop_time_window
            self.waiting_for_letter = False
            self.key_buff = []
            self.wait_for_module("keyboard")
            self.keys = [keyboard.Key.shift, keyboard.Key.shift_r]
            self.loop()
        else:
            self.main(
                task=task,
            )

    def main(self, task):
        "execcuted by self.loop or at the end of __init__"
        self.log(f"Will use prompt {self.whisper_prompt} and task {task}")

        self.wait_for_module("tempfile")
        file = tempfile.NamedTemporaryFile(suffix=".mp3").name
        min_duration = 2  # if the recording is shorter, exit

        # Kill any previously running recordings
        start_time = time.time()
        self.wait_for_module("subprocess")
        subprocess.run(
            ["killall", "rec"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        # Start recording
        self.log(f"Recording {file}")
        subprocess.Popen(f"rec -r 44000 -c 1 -b 16 {file} &", shell=True)

        self.notif("Listening")
        self.wait_for_module("playsound")
        self.playsound("sounds/Slick.ogg")

        if self.gui is True:
            # Show recording form
            whisper_prompt, LLM_instruction = self.gui(
                self.whisper_prompt,
                task,
                )
        else:
            whisper_prompt = self.whisper_prompt
            LLM_instruction = self.LLM_instruction
            self.wait_for_module("keyboard")
            def released_shift(key):
                "detect when shift is pressed"
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
        self.playsound("sounds/Rhodes.ogg")
        if self.gui is False:
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

        if self.sound_cleanup:
            # clean up the sound
            self.log("Cleaning up sound")

            self.wait_for_module("torchaudio")
            self.wait_for_module("sf")
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
        self.wait_for_module("transcription")
        with open(file, "rb") as f:
            transcript_response = transcription(
                model="whisper-1",
                file=f,
                language=self.whisper_lang,
                prompt=whisper_prompt,
                temperature=0,
                max_retries=0,
            )
        text = transcript_response.text
        self.notif(self.log(f"Transcript: {text}"))

        if task == "write":
            self.wait_for_module("pyclip")
            try:
                clipboard = pyclip.paste()
            except Exception as err:
                self.log(f"Erasing the previous clipboard because error when loding it: {err}")
                clipboard = ""

            if LLM_instruction:
                self.log(
                    f"Calling {self.llm_model} to transfrom the transcript to follow "
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
                self.wait_for_module("json")
                self.log(f"Messages sent to LLM:\n{json.dumps(messages, indent=4, ensure_ascii=False)}")

                self.wait_for_module("completion")
                LLM_response = completion(
                    model=self.llm_model,
                    messages=messages,
                )
                answer = LLM_response.json(
                )["choices"][0]["message"]["content"]
                self.log(f'LLM output: "{answer}"')
                text = answer

            self.log("Pasting clipboard")
            pyclip.copy(text)
            if self.auto_paste:
                os.system("xdotool key ctrl+v")
                pyclip.copy(clipboard)
                self.log("Clipboard reset")

            self.notif("Done")
            self.playsound("sounds/Positive.ogg")

        elif task == "transform_clipboard":
            self.log(
                f'Calling LLM with instruction "{text}" and tasked to transform the clipboard'
            )

            self.wait_for_module("pyclip")
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
            self.wait_for_module("completion")
            LLM_response = completion(
                model=self.llm_model,
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
            pyclip.copy(answer)
            self.notif(answer, -1)
            if self.auto_paste:
                os.system("xdotool key ctrl+v")
                pyclip.copy(clipboard)
                self.log("Clipboard reset")

            self.playsound("sounds/Positive.ogg")

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
            self.wait_for_module("completion")
            LLM_response = completion(model=self.llm_model, messages=messages)
            answer = LLM_response.json()["choices"][0]["message"]["content"]
            self.log(f'LLM answer to the chat: "{answer}"')
            self.notif(answer, -1)

            vocal_file_mp3 = tempfile.NamedTemporaryFile(suffix=".mp3").name
            voice_engine = self.voice_engine if not self.disable_voice else None
            if voice_engine == "piper":
                self.wait_for_module("wave")
                self.wait_for_module("voice")
                try:
                    self.log(f"Synthesizing speech to {vocal_file_mp3}")
                    with wave.open(vocal_file_mp3, "wb") as wav_file:
                        answer = answer.replace("!", ".")
                        answer = answer.replace(". ", ".\n")
                        voice.synthesize(answer, wav_file)

                    self.log(f"Playing voice file: {vocal_file_mp3}")
                    self.playsound(vocal_file_mp3)
                except Exception as err:
                    self.notif(
                        self.log(f"Error with piper, trying with espeak: '{err}'"))
                    voice_engine = "espeak"

            if voice_engine == "openai":
                self.wait_for_module("OpenAI")
                try:
                    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
                    response = client.audio.speech.create(
                        model="tts-1",
                        voice="echo",
                        input=answer,
                        response_format="mp3",
                        speed=1,
                    )
                    response.stream_to_file(vocal_file_mp3)
                    self.playsound(vocal_file_mp3)
                except Exception as err:
                    self.notif(
                        self.log(f"Error with openai voice_engine, trying with espeak: '{err}'"))
                    voice_engine = "espeak"

            if voice_engine == "espeak":
                if self.whisper_lang:
                    subprocess.run(
                        ["espeak", "-v", self.whisper_lang, "-p", "20", "-s", "110", "-z", answer]
                    )
                else:
                    subprocess.run(
                        ["espeak", "-p", "20", "-s", "110", "-z", answer]
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

    def loop(self):
        "run continuously, waiting for shift to be pressed enough times"
        while True:
            listener = keyboard.Listener(
                on_release=self.on_release,
            )
            listener.start()  # non blocking

            self.notif("Loop started.")
            listener.join()

    def on_release(self, key):
        "triggered when a key is released"
        if key in self.keys:
            self.log("Released shift")
            self.log(f"Shift counter: {len(self.key_buff)}")

            self.key_buff.append(time.time())

            # remove if too old
            self.key_buff = [
                t
                for t in self.key_buff
                if time.time() - t <= self.loop_time_window
            ]

            if len(self.key_buff) == self.loop_shift_nb:
                self.waiting_for_letter = True
                self._notif("Waiting for task letter:\nw(rite)\nn(ew voice chat)\nc(ontinue voice chat)\nt(ransform_clipboard)\n\nSettings:\nS(toggle voice)", self.loop_time_window)


        elif self.waiting_for_letter:
            self.key_buff = []
            self.waiting_for_letter = False

            if not hasattr(key, "char"):
                return

            if key.char not in ["w", "n", "c", "t", "s"]:
                self._notif(f"Unexpected key: '{key.char}'")
                return

            if key.char == "n":
                self._notif("Started voice chat")
                task = "new_voice_chat"

            elif key.char == "c":
                self._notif("Continuing voice chat")
                task = "continue_voice_chat"

            elif key.char == "w":
                self._notif("writing mode")
                task = "write"

            elif key.char == "t":
                self._notif("transform_clipboard mode")
                task = "transform_clipboard"

            elif key.char == "s":
                if not self.voice_engine:
                    self._notif("Can't toggle voice if voice_engine was never set")
                elif self.disable_voice:
                    self.disable_voice = False
                    self._notif("Enabling voice")
                else:
                    self.disable_voice = True
                    self._notif("Disabling voice")
                return

            else:
                self._notif(f"Unexpected key pressed: {key}")
                return
            self.main(task=task)

        else:
            self.key_buff = []
            self.log(f"Pressed: {key}")

    def log(self, message: str, do_print: bool=False) -> str:
        "add string to the log"
        if self.verbose or do_print:
            print(message)
        with open("texts.log", "a") as f:
            f.write(f"{int(time.time())} {message}\n")
        return message

    def notif(self, message: str, timeout: int = 5) -> str:
        "notification to the computer"
        if self.disable_notifications:
            self.log(f"Notif: '{message}'")
            return message
        self._notif(message, timeout)

    def _notif(self, message: str, timeout: int = 5) -> str:
        self.log(f"Notif: '{message}'")
        notification.notify(title="Quick Whisper", message=message, timeout=timeout)

    def playsound(self, name: str) -> None:
        "create a thread to play sounds without blocking the main code"
        if self.disable_bells:
            return
        if hasattr(self, "sound_queue"):
            self.sound_queue.put(name)
        else:
            def sound_thread(qin:queue.Queue) -> None:
                "play sound when receiving a path from the queue"
                global playsound
                while True:
                    name = qin.get()
                    if not name:
                        return  # kill thread
                    playsound(name)
            self.sound_queue = queue.Queue()
            self.sound_thread = threading.Thread(
                target=sound_thread,
                args=(self.sound_queue,),
                daemon=False,
            )
            self.sound_thread.start()
            self.sound_queue.put(name)

    def gui(self, prompt: str, task: str) -> str:
        "create a popup to manually enter a prompt"
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

    def wait_for_module(self, module: str, timeout: int = 10) -> None:
        "sleep while the module is not imported by importer"
        cnt = 0
        start = time.time()
        while time.time() - start < timeout:
            if module in globals():
                return
            assert self.import_thread.is_alive(), "Importer thread not running, it encountered an error"
            time.sleep(0.001)
            cnt += 1
            if self.verbose and cnt % 10 == 0:
                print(f"WAITING FOR {module}")
        raise Exception(f"Module not imported in time: {module}")


def importer(import_list: List[str]) -> None:
    """
    multithreading to import module and reduce startup time
    source: https://stackoverflow.com/questions/46698837/can-i-import-modules-from-thread-in-python
    """
    global playsound, notification, tempfile, subprocess, sg, keyboard, torchaudio, sf, completion, transcription, pyclip, json, piper, wave, voice, OpenAI
    for import_str in import_list:
        if DEBUG_IMPORT:
            print(f"Importing: '{import_str}'")
        try:
            exec(import_str, globals())
        except Exception as err:
            raise Exception(f"Error when importing module '{import_str}': {err}'")
    if DEBUG_IMPORT:
        print("Done importing all packages.")


if __name__ == "__main__":
    import fire
    args, kwargs = fire.Fire(lambda *args, **kwargs: [args, kwargs])
    if args:
        raise Exception(f"Non keyword args are not supported: {args}")

    if "help" in kwargs:
        print(help(QuickWhisper))
        raise SystemExit()

    if "loop" in kwargs and kwargs["loop"]:
        from playsound import playsound as playsound
        from plyer import notification as notification
        import tempfile
        import subprocess
        import PySimpleGUI as sg
        from pynput import keyboard
        import os
        import torchaudio
        import soundfile as sf
        from litellm import completion, transcription
        import json
        import pyclip
        from piper.voice import PiperVoice as piper
        import wave
        from openai import OpenAI

    try:
        QuickWhisper(**kwargs)
        raise SystemExit("Done")
    except Exception as err:
        import os
        os.system("killall rec")
        from plyer import notification
        notification.notify(title="Quick Whisper", message=f"Error: {err}", timeout=-1)
        raise
