import sys
from typing import List, Optional, Union
import threading
import queue
from pathlib import Path
import time
import platform
from platformdirs import user_cache_dir
import requests
import os
import psutil
try:
    from uuid6 import uuid6 as uuid
except Exception:
    from uuid import uuid4 as uuid

# make litellm way faster to launch
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

assert Path(user_cache_dir()).exists(), f"User cache dir not found: '{user_cache_dir()}'"
cache_dir = Path(user_cache_dir()) / "QuickWhisperTyper"
cache_dir.mkdir(exist_ok=True)

DEBUG_IMPORT = False

os_type = platform.system()

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
    allowed_voice_engine = ("openai", "piper", "espeak", "deepgram", None)

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
        restore_clipboard: bool = False,
        sound_cleanup: bool = False,
        whisper_prompt: str = None,
        whisper_lang: str = None,
        voice_engine: str = None,
        piper_model_path: str = None,
        disable_voice: bool = False,
        LLM_instruction: str = None,
        gui: bool = False,
        loop: bool = False,
        loop_shift_nb: int = 3,
        loop_time_window: int = 2,
        loop_tasks: dict = {"n":{"task":"new_voice_chat"}, "c": {"task":"continue_voice_chat"}, "w": {"task": "write"}, "t": {"task": "transform_clipboard"}, "s": {"extra_args": "disable_voice"}},
        verbose: bool = False,
        disable_bells: bool = False,
        disable_notifications: bool = False,
        deepgram_transcription: bool = False,
        custom_transcription_url: Optional[str] = None,
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
            if True, will trigger ctrl+v to paste directly.

        restore_clipboard: bool, default False
            wether to automatically restore your previous clipboard if
            auto_paste is used.

        sound_cleanup: bool, default False
            Clean up the sound before sending it to whisper, but this adds
            latency depending of how powerful your computer is.
            This uses sox, to modify the arguments, look at the value
            of self.sox_cleanup

        whisper_prompt: str, default None
            prompt to given to whisper

        whisper_lang: str, default None

        voice_engine, default None
            piper, openai, espeak, deepgram, None
            For deepgram, only english language is supported.

        piper_model_path: str, default None
            name of a piper model file.
            For example 'en_US-lessac-medium'. Make sure you have 
            a .onxx and .json file present.
            More info: https://github.com/rhasspy/piper

        disable_voice: bool, default False
            This flag disables the voice_engine. It can be used to toggle on
            or off the voice_engine in the loop.

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

        loop_tasks: dict, default {"n":{"task":"new_voice_chat"}, "c": {"task":"continue_voice_chat"}, "w": {"task": "write"}, "t": {"task": "transform_clipboard"}, "s": {"extra_args": "disable_voice"}},
            A dict that defines what task to trigger when the loop is triggered
            each key must be a single letter
            each value must be a dict with arguments
            if a value of the arguments is a filepath, it will be replaced by the file's content (useful to add long prompts)
            You always have to specify a "task" key/val except to toggle the voice via {"extra_args": "disable_voice"}

        verbose: bool, default False

        disable_bells: bool, default False
            disable sound feedback

        disable_notifications: bool, default False
            disable notifications, except for the loop trigger

        deepgram_transcription: bool, default False
            if True, use deepgram instead of openai's whisper for transcription.
            whisper_prompt and whisper_lang will be ignored.
            Python >=3.10 is needed
            Incompatible with custom_transcription_url

        custom_transcription_url: str
            if set to for example "http://127.0.0.1:8080/inference" then the
            audio file will be send there for transcription.
            You can try with whispercpp with this command for example:
            `./server -m models/small_acft_q8_0.bin --threads 8 --audio-ctx 1500 -l fr --no-gpu --debug-mode --convert -p 1`
            Incompatible with deepgram_transcription

        """
        if verbose:
            global DEBUG_IMPORT
            DEBUG_IMPORT = True
        assert not (custom_transcription_url and deepgram_transcription), "Cannot use a custom transcription url and ask for deepgram!"

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
            "from playsound import playsound",
            "from plyer import notification",
        ]
        if os_type == "Linux":
            to_import.append("import subprocess")
        else:
            to_import.append("from plyer import audio_recorder")
        if gui:
            to_import.append("import PySimpleGUI as sg")
        else:
            to_import.append("from pynput import keyboard")
        to_import.append("import os")
        if sound_cleanup:
            to_import.append("import torchaudio")
            to_import.append("import soundfile as sf")
        if not deepgram_transcription:
            to_import.append("from litellm import completion, transcription")
        else:
            assert int(sys.version.split(".")[1]) >= 10, "deepgram needs python 3.10+"
            to_import.append("from litellm import completion")
            to_import.append("from deepgram import DeepgramClient, PrerecordedOptions")
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
                elif voice_engine == "deepgram":
                    to_import.append("from deepgram import DeepgramClient, ClientOptionsFromEnv, SpeakOptions")

        self.import_thread = threading.Thread(target=importer, args=(to_import,), daemon=False)
        self.import_thread.start()

        # store arguments
        self.verbose = verbose
        self.gui = gui
        self.llm_model = llm_model
        self.voice_engine = voice_engine
        self.piper_model_path = piper_model_path
        self.auto_paste = auto_paste
        self.restore_clipboard = restore_clipboard
        self.sound_cleanup = sound_cleanup
        self.LLM_instruction = LLM_instruction
        self.whisper_lang = whisper_lang
        self.whisper_prompt = whisper_prompt
        self.disable_notifications = disable_notifications
        self.disable_bells = disable_bells
        self.disable_voice = disable_voice
        self.deepgram_transcription = deepgram_transcription
        self.custom_transcription_url = custom_transcription_url

        self.wait_for_module("keyboard")
        self.loop_key_triggers = [keyboard.Key.shift, keyboard.Key.shift_r]

        if loop:
            # the module were imported already
            if isinstance(loop_tasks, str):
                self.wait_for_module("json")
                try:
                    loop_tasks = json.loads(loop_tasks)
                except Exception as err:
                    raise Exception(f"Error when parsing loop_tasks as a dict: '{err}'")
            assert isinstance(loop_tasks, dict), f"loop_tasks must be a dict, not {type(loop_tasks)}"
            assert loop_tasks, "loop_tasks must not be empty"
            assert all(isinstance(val, dict) for val in loop_tasks.values()), "values of loop_tasks must be dictionnaries"
            assert all(val for val in loop_tasks.values()), "values of loop_tasks can't be empty"

            # replace any path in values by its content
            for k, v in loop_tasks.items():
                for kk, vv in v.items():
                    if Path(vv).exists():
                        loop_tasks[k][kk] = Path(vv).read_text()

            self.loop_tasks = loop_tasks
            self.loop_shift_nb = loop_shift_nb
            self.loop_time_window = loop_time_window
            self.waiting_for_letter = False
            self.key_buff = []
            self.wait_for_module("keyboard")
            self.loop()
        else:
            self.main(
                task=task,
                auto_paste=auto_paste,
                gui=gui,
                whisper_prompt=whisper_prompt,
                whisper_lang=whisper_lang,
                LLM_instruction=LLM_instruction,
                sound_cleanup=sound_cleanup,
                llm_model=llm_model,
                voice_engine=voice_engine,
                disable_voice=disable_voice,
                restore_clipboard=restore_clipboard,
            )

    def main(
        self,
        task: str,
        auto_paste: Optional[bool] = None,
        gui: Optional[bool] = None,
        whisper_prompt: Optional[str] = None,
        whisper_lang: Optional[str] = None,
        LLM_instruction: Optional[str] = None,
        sound_cleanup: Optional[bool] = None,
        llm_model: Optional[str] = None,
        voice_engine: Optional[str] = None,
        disable_voice: Optional[bool] = None,
        restore_clipboard: Optional[bool] = None,
        custom_transcription_url: Optional[str] = None
        ):
        "execcuted by self.loop or at the end of __init__"

        # set the main args to the launch value if not set by the loop
        if auto_paste is None and self.auto_paste:
            auto_paste = self.auto_paste
        if gui is None and self.gui:
            gui = self.gui
        if whisper_prompt is None and self.whisper_prompt:
            whisper_prompt = self.whisper_prompt
        if whisper_lang is None and self.whisper_lang:
            whisper_lang = self.whisper_lang
        if LLM_instruction is None and self.LLM_instruction:
            LLM_instruction = self.LLM_instruction
        if sound_cleanup is None and self.sound_cleanup:
            sound_cleanup = self.sound_cleanup
        if llm_model is None and self.llm_model:
            llm_model = self.llm_model
        if voice_engine is None and self.voice_engine:
            voice_engine = self.voice_engine
        if disable_voice is None and self.disable_voice:
            disable_voice = self.disable_voice
        if restore_clipboard is None and self.restore_clipboard:
            restore_clipboard = self.restore_clipboard
        if custom_transcription_url is None and self.custom_transcription_url:
            custom_transcription_url = self.custom_transcription_url

        self.log(f"Will use prompt {self.whisper_prompt} and task {task}")

        file = cache_dir / (str(uuid()) + ".mp3")
        min_duration = 2  # if the recording is shorter, exit

        # Start recording
        start_time = time.time()
        self.stop_recording()  # just in case
        self.log(f"Recording {file}")
        if os_type == "Linux":
            # Kill any previously running recordings
            self.rec_process = subprocess.Popen(f"timeout 1h rec -r 44000 -c 1 -b 16 {file}", shell=True)
        else:
            self.wait_for_module("audio_recorder")
            audio_recorder.start(
                file_path=file,
                channels=1,
                sample_rate=44100,
                bit_rate=128000,
            )
        self.notif("Listening")
        self.wait_for_module("playsound")
        playsound("sounds/Slick.ogg", block=False)

        if gui is True:
            # Show recording form
            whisper_prompt, LLM_instruction = self.launch_gui(
                whisper_prompt,
                task,
                )
        else:
            keys = self.loop_key_triggers
            def released_shift(key):
                "detect when shift is pressed"
                if key in keys:
                    self.log("Pressed shift.")
                    time.sleep(1)
                    return False
                elif key in [keyboard.Key.esc, keyboard.Key.space]:
                    self.notif(self.log("Pressed escape or spacebar: quitting."))
                    self.stop_recording()
                    raise SystemExit("Quitting.")

            with keyboard.Listener(on_release=released_shift) as listener:
                self.log("Shortcut listener started, press shift to stop recording, esc or spacebar to quit.")

                listener.join()  # blocking

        # Kill the recording
        self.stop_recording()
        end_time = time.time()
        self.log(f"Done recording {file}")
        playsound("sounds/Rhodes.ogg", block=False)
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
        text = None
        if custom_transcription_url:
            self.log(f"Calling server at {custom_transcription_url}")

            headers = {
                # 'Content-Type': 'multipart/form-data'
            }
            data = {
                'temperature': '0.0',
                'temperature_inc': '0.2',
                'response_format': 'json'
            }
            try:
                with open(file, "rb") as f:
                    response = requests.post(
                        custom_transcription_url,
                        headers=headers,
                        files={'file': f},
                        data=data
                    )
                response.raise_for_status()
                transcript_response = response.json()
                if "error" in transcript_response:
                    self.log(f"Transcription error: {transcript_response['error']}")
                    raise Exception(transcript_response["error"])
                text = transcript_response["text"]
                assert text.strip(), "Empty text found"
            except Exception as err:
                self.log(f"Error when using request: '{err}'\nTrying another way.")

        if text is None and (not self.deepgram_transcription):
            self.log("Calling whisper")
            self.wait_for_module("transcription")
            with open(file, "rb") as f:
                transcript_response = transcription(
                    model="whisper-1",
                    file=f,
                    language=whisper_lang,
                    prompt=whisper_prompt,
                    temperature=0,
                    max_retries=3,
                )
            text = transcript_response.text


        if text is None:
            assert self.deepgram_transcription
            self.log("Calling deepgram")
            try:
                deepgram = DeepgramClient()
            except Exception as err:
                raise Exception(f"Error when creating deepgram client: '{err}'")
            # set options
            options = dict(
                # docs: https://playground.deepgram.com/?endpoint=listen&smart_format=true&language=en&model=nova-2
                model="nova-2",

                detect_language=True,
                # not all features below are available for all languages

                # intelligence
                summarize=False,
                topics=False,
                intents=False,
                sentiment=False,

                # transcription
                smart_format=True,
                punctuate=True,
                paragraphs=True,
                utterances=True,
                diarize=False,

                # redact=None,
                # replace=None,
                # search=None,
                # keywords=None,
                # filler_words=False,
            )
            options = PrerecordedOptions(**options)
            with open(file, "rb") as f:
                payload = {"buffer": f.read()}
            content = deepgram.listen.prerecorded.v("1").transcribe_file(
                payload,
                options,
            ).to_dict()
            assert len(content["results"]["channels"]) == 1, "unexpected deepgram output"
            assert len(content["results"]["channels"][0]["alternatives"]) == 1, "unexpected deepgram output"
            text = content["results"]["channels"][0]["alternatives"][0]["paragraphs"]["transcript"].strip()
            assert text, "Empty text from deepgram transcription"

        assert text is not None, "Text should not be None at this point"
        self.notif(self.log(f"Transcript: {text}"))

        if task == "write":
            self.wait_for_module("pyclip")
            try:
                clipboard = pyclip.paste()
            except Exception as err:
                self.log(f"Erasing the previous clipboard because error when loading it: {err}")
                clipboard = ""

            if LLM_instruction:
                self.log(
                    f"Calling {llm_model} to transfrom the transcript to follow "
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
                    model=llm_model,
                    messages=messages,
                    num_retries=3,
                )
                answer = LLM_response.json(
                )["choices"][0]["message"]["content"]
                self.log(f'LLM output: "{answer}"')
                text = answer

            self.log("Pasting clipboard")
            pyclip.copy(text)
            if auto_paste:
                cont = keyboard.Controller()
                modifier = keyboard.Key.ctrl if os_type != "Darwin" else keyboard.Key.cmd
                with cont.pressed(modifier):
                    cont.press("v")
                    cont.release("v")
                if restore_clipboard:
                    pyclip.copy(clipboard)
                    self.log("Clipboard restored")

            self.notif("Done")
            playsound("sounds/Positive.ogg", block=False)

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
                model=llm_model,
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
            if auto_paste:
                cont = keyboard.Controller()
                modifier = keyboard.Key.ctrl if os_type != "Darwin" else keyboard.Key.cmd
                with cont.pressed(modifier):
                    cont.press("v")
                    cont.release("v")
                if restore_clipboard:
                    pyclip.copy(clipboard)
                    self.log("Clipboard restored")

            playsound("sounds/Positive.ogg", block=False)

        elif "voice_chat" in task:
            if "new" in task:
                voice_file = cache_dir / f"quick_whisper_chat_{int(time.time())}.txt"
                self.log(f"Creating new voice chat file: {voice_file}")

                messages = [
                    {"role": "system", "content": self.system_prompts["voice"]},
                ]

            elif "continue" in task:
                voice_files = [
                    f
                    for f in cache_dir.iterdir()
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
            LLM_response = completion(model=llm_model, messages=messages)
            answer = LLM_response.json()["choices"][0]["message"]["content"]
            self.log(f'LLM answer to the chat: "{answer}"')
            self.notif(answer, -1)

            vocal_file_mp3 = cache_dir / (str(uuid()) + ".mp3")
            voice_engine = voice_engine if not disable_voice else None
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
                    playsound(vocal_file_mp3, block=True)
                except Exception as err:
                    self.notif(
                        self.log(f"Error with piper, trying with espeak: '{err}'"))
                    voice_engine = "espeak"

            if voice_engine == "deepgram":
                self.wait_for_module("DeepgramClient")
                try:
                    deepgram = DeepgramClient(
                        api_key="",
                        config=ClientOptionsFromEnv()
                    )
                    options = SpeakOptions(
                        model="aura-asteria-en",
                    )
                    response = deepgram.speak.v("1").save(
                        vocal_file_mp3,
                        {"text": answer},
                        options,
                    )
                    playsound(vocal_file_mp3, block=True)
                except Exception as err:
                    self.notif(
                        self.log(f"Error with deepgram voice_engine, trying with espeak: '{err}'"))
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
                        speed=1.3,
                    )
                    response.stream_to_file(vocal_file_mp3)
                    playsound(vocal_file_mp3, block=True)
                except Exception as err:
                    self.notif(
                        self.log(f"Error with openai voice_engine, trying with espeak: '{err}'"))
                    voice_engine = "espeak"

            if voice_engine == "espeak":
                if whisper_lang:
                    subprocess.run(
                        ["espeak", "-v", whisper_lang, "-p", "20", "-s", "110", "-z", answer]
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

    def loop(self) -> None:
        "run continuously, waiting for shift to be pressed enough times"
        failed = 0
        while failed <= 3:
            try:
                listener = keyboard.Listener(
                    on_release=self.on_release,
                )
                listener.start()  # non blocking

                self.notif("Starting new loop", timeout=1)
                listener.join()
            except KeyboardInterrupt:
                self.log("Quitting.", True)
                raise SystemExit()
            except Exception as err:
                failed += 1
                self._notif(f"Error #{failed} in loop: '{err}'")
            finally:
                try:
                    if "listener" in locals():
                        listener.stop()
                except Exception as err:
                    self._notif(f"Error: failed to stop listener: '{err}'")
        raise Exception(f"{failed} errors in loop: crashing")

    def on_release(
        self,
        key,  # : keyboard.Key
        ) -> Union[bool, None]:
        "triggered when a key is released"
        if key in self.loop_key_triggers:
            if self.verbose:
                print("Released loop key trigger")
                print(f"Trigger counter: {len(self.key_buff)}")

            self.key_buff.append(time.time())

            # remove if too old
            self.key_buff = [
                t
                for t in self.key_buff
                if time.time() - t <= self.loop_time_window
            ]

            if len(self.key_buff) == self.loop_shift_nb:
                self.waiting_for_letter = True
                self._notif(f"Waiting for task letter:\n{','.join(self.loop_tasks.keys())}", self.loop_time_window)


        elif self.waiting_for_letter:
            self.key_buff = []
            self.waiting_for_letter = False

            if not hasattr(key, "char"):
                return False

            if key.char not in self.loop_tasks.keys():
                self._notif(f"Unexpected key: '{key.char}'")
                return False

            main_args = self.loop_tasks[key.char]
            message = ""
            for k, v in main_args.items():
                k = str(k)[:20]
                v = str(v)[:20]
                message += f"{k}: {v}\n"
            self._notif(f"Started loop with arg:\n{message.strip()}")

            if "extra_args" in main_args and main_args["extra_args"] == "disable_voice":
                if not self.voice_engine:
                    self._notif("Can't toggle voice if voice_engine was never set")
                elif self.disable_voice:
                    self.disable_voice = False
                    self._notif("Enabling voice")
                else:
                    self.disable_voice = True
                    self._notif("Disabling voice")
                return False

            if "task" not in main_args and main_args["task"] in self.allowed_tasks:
                self._notif(f"Invalid task in '{main_args}'")
                return False

            self.main(**main_args)
            return False

        else:
            self.key_buff = []
            # self.log(f"Pressed: {key}")

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

    def check_sound(self) -> bool:
        try:
            out = self.sound_queue_out.get_nowait()
        except queue.Empty:
            out = None
        if out:
            self._notif(f"Error when playing last sound: {out}")
            return False
        else:
            return True

    def launch_gui(self, prompt: str, task: str) -> str:
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
            self.stop_recording()
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

    def stop_recording(self) -> None:
        self.log("Trying to stop recording")
        if os_type == "Linux":
            self.wait_for_module("subprocess")
            if hasattr(self, "rec_process"):
                children = psutil.Process(self.rec_process.pid).children()
                assert children, "It seems the rec_process has no children"
                for child in children:
                    child.terminate()

                delattr(self, "rec_process")
        else:
            self.wait_for_module("audio_recorder")
            audio_recorder.stop()
        return


def importer(import_list: List[str]) -> None:
    """
    multithreading to import module and reduce startup time
    source: https://stackoverflow.com/questions/46698837/can-i-import-modules-from-thread-in-python
    """
    global playsound, notification, subprocess, sg, keyboard, torchaudio, sf, completion, transcription, pyclip, json, piper, wave, voice, OpenAI, DeepgramClient, PrerecordedOptions, ClientOptionsFromEnv, SpeakOptions
    for import_str in import_list:
        if DEBUG_IMPORT:
            print(f"Importing: '{import_str}'")
        try:
            exec(import_str, globals())
        except Exception as err:
            if "playsound" in import_str:
                try:
                    exec("from playsound3 import playsound", globals())
                    continue
                except Exception as err:
                    raise Exception(f"Couldn't import either playsound or playsound3: '{err}'")
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
        try:
            from playsound import playsound
        except Exception:
            try:
                from playsound3 import playsound as playsound
            except Exception as err:
                raise Exception(f"Couldn't import either playsound or playsound3: '{err}'")
        from plyer import notification as notification
        if os_type == "Linux":
            import subprocess
        else:
            from plyer import notification as audio_recorder
        if "--gui" in args or ("gui" in kwargs and kwargs["gui"]):
            import PySimpleGUI as sg
        from pynput import keyboard
        import os
        import torchaudio
        import soundfile as sf
        from litellm import completion, transcription
        from deepgram import DeepgramClient, PrerecordedOptions, ClientOptionsFromEnv, SpeakOptions
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
