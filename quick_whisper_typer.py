from pathlib import Path
import tempfile
import subprocess
import time


# import pyautogui

# Set up variables and prompts
prompts = {
    "fr": None,
    "en": None,
    # "fr": "Dictee voicee sur mon telephone: ",
    # "en": "Dictation on my smartphone: "
}
system_prompts = {
    "voice": "You are a helpful assistant. I am in a hurry and your answers will be played on speaker so use as few words as you can while remaining helpful and truthful. Don't use too short sentences otherwise the speakers will crash.",
    "transform_clipboard": "You transform INPUT_TEXT according to an instruction. Only reply the transformed text without anything else.",
}
speaker_models = {"fr": "fr_FR-gilles-low", "en": "en_US-lessac-medium"}
allowed_tasks = (
    "transform_clipboard",
    "new_voice_chat",
    "continue_voice_chat",
    "write",
    "custom",
)

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


def log(message):
    print(message)
    with open("texts.log", "a") as f:
        f.write(f"{int(time.time())} {message}\n")
    return message


def notif(message):
    from plyer import notification

    notification.notify(title="Quick Whisper", message=message, timeout=-1)


def popup(prompt, task, lang):
    import PySimpleGUI as sg

    title = "Sound Recorder"

    layout = [
        [sg.Text(f"TASK: {task}\nLANG: {lang}")],
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
        log(f"Whisper prompt: {whisper_prompt} for task {task}")
        return whisper_prompt, LLM_instruction
    else:
        log("Pressed cancel or escape. Exiting.")
        subprocess.run(
            ["killall", "rec"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        raise SystemExit()


class QuickWhisper:
    def __init__(
        self,
        lang,
        task,
        model="openai/gpt-3.5-turbo-0125",
        auto_paste=False,
        gui=False,
        sound_cleanup=False,
        voice_engine=None,
        whisper_prompt=None,
        LLM_instruction=None,
        daemon_mode=False,
    ):
        """
        Parameters
        ----------
        lang
            fr, en
        task
            transform_clipboard, write, voice_chat
        model: str, default "openai/gpt-3.5-turbo-0125"
        auto_paste, default False
            if True, will use xdotool to paste directly. Otherwise just plays
            a sound to tell you that the clipboard was filled.
        gui, default to False
            if True, a window will open to allow to enter specific prompts etc
            if False, no window is used and you have to press shift to stop the recording.
        sound_cleanup: bool, default False
            if True, will try to clean up the sound before sending it to whisper
        voice_engine, default None
            piper, openai, espeak, None
        whisper_prompt: str
            default to None
        LLM_instruction: str
            if given, then the transcript will be given to an LLM and tasked
            to modify it according to those instructions. Meaning this is
            the system prompt.
        daemon_mode
            default to False. Designed for loop.py Is either False or a queue
            that stops listening when an item is received.
            if True, gui argument is ignored
        """
        # Checking if the language is supplied and correct
        allowed_langs = ("fr", "en")
        assert (
            lang != "" and lang in allowed_langs
        ), f"Invalid lang {lang} not part of {allowed_langs}"

        if gui is True:
            assert (
                not whisper_prompt
            ), "whisper_prompt already given, shouldn't launch gui"
            assert (
                not LLM_instruction
            ), "whisper_prompt already given, shouldn't launch gui"

        if gui or LLM_instruction:
            assert "/" in model, f"LLM model name must be given in litellm format"

        # Checking voice engine
        if voice_engine == "None":
            voice_engine = None
        allowed_voice_engine = ("openai", "piper", "espeak", None)
        assert (
            "voice" not in task or voice_engine in allowed_voice_engine
        ), f"Invalid voice engine {voice_engine} not part of {allowed_voice_engine}"

        # Selecting prompt based on language
        if not whisper_prompt:
            whisper_prompt = prompts[lang]

        # Checking that the task is allowed
        task = task.replace("-", "_").lower()
        assert (
            task != "" and task in allowed_tasks
        ), f"Invalid task {task} not part of {allowed_tasks}"

        log(f"Will use language {lang} and prompt {whisper_prompt} and task {task}")

        file = tempfile.NamedTemporaryFile(suffix=".mp3").name
        min_duration = 2  # if the recording is shorter, exit

        # Kill any previously running recordings
        start_time = time.time()
        subprocess.run(
            ["killall", "rec"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        # Start recording
        log(f"Recording {file}")
        subprocess.Popen(f"rec -r 44000 -c 1 -b 16 {file} &", shell=True)
        time.sleep(0.2)  # delay to properly recod
        from playsound import playsound

        playsound("sounds/Slick.ogg")

        if daemon_mode is not False:
            if daemon_mode.get() == "STOP":
                raise NotImplementedError()
        elif gui is True:
            # Show recording form
            whisper_prompt, LLM_instruction = popup(whisper_prompt, task, lang)
        else:
            from pynput import keyboard

            def released_shift(key):
                if key == keyboard.Key.shift:
                    log("Pressed shift.")
                    time.sleep(1)
                    return False

            listener = keyboard.Listener(on_release=released_shift)

            listener.start()  # non blocking
            log("Shortcut listener started, press shift to exit")

            # import last minute to be quicker to launch
            import soundfile as sf
            import torchaudio

            listener.join()  # blocking

        # Kill the recording
        subprocess.run(
            ["killall", "rec"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        end_time = time.time()
        log(f"Done recording {file}")
        if gui is False:
            playsound("sounds/Rhodes.ogg")

        # clean up the sound
        log("Cleaning up sound")

        if sound_cleanup:
            # fast if already imported
            import soundfile as sf
            import torchaudio

            try:
                waveform, sample_rate = torchaudio.load(file)
                waveform, sample_rate = torchaudio.sox_effects.apply_effects_tensor(
                    waveform,
                    sample_rate,
                    sox_cleanup,
                )
                file2 = file.replace(".mp3", "") + "_clean.wav"
                sf.write(str(file2), waveform.numpy().T,
                         sample_rate, format="wav")
                file = file2
            except Exception as err:
                log(f"Error when cleaning up sound: {err}")

        # Check duration
        duration = end_time - start_time
        log(f"Duration {duration}")
        if duration < min_duration:
            notif(
                log(
                    f"Recording too short ({duration} s), exiting without calling whisper."
                )
            )
            raise SystemExit()

        from openai import OpenAI

        # Load OpenAI api key from file
        with open("OPENAI_API_KEY.txt", "r") as f:
            api_key = f.read().strip()
            client = OpenAI(api_key=api_key)

        # Call whisper
        log("Calling whisper")
        with open(file, "rb") as f:
            transcript_response = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language=lang,
                prompt=whisper_prompt,
                temperature=0,
            )
        text = transcript_response.text
        notif(log(f"Transcript: {text}"))

        import pyclip

        from litellm import completion
        import os

        for path in list(Path(".").rglob("./*API_KEY.txt")):
            backend = path.name.split("_API_KEY.txt")[0]
            content = path.read_text().strip()
            os.environ[f"{backend.upper()}_API_KEY"] = content

        if task == "write":
            clipboard = pyclip.paste()
            if not clipboard:
                log("Clipboard is empty, this is not compatible with the task")
                raise SystemExit()
            log(f"Clipboard previous content: '{clipboard}'")

            if LLM_instruction:
                log(
                    f"Calling {model} to transfrom the transcript to follow "
                    f"those instructions: {LLM_instruction}"
                )
                LLM_response = completion(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": LLM_instruction,
                        },
                        {
                            "role": "user",
                            "content": f"INPUT_TEXT: '{clipboard}'\n\nINSTRUCTION: '{text}'",
                        },
                    ],
                )
                answer = LLM_response.json(
                )["choices"][0]["message"]["content"]
                log(f'LLM output: "{answer}"')
                text = answer

            log("Pasting clipboard")
            # pyautogui.click()
            pyclip.copy(text)
            if auto_paste:
                os.system("xdotool key ctrl+v")
                pyclip.copy(clipboard)
                log("Clipboard reset")
            playsound("sounds/Positive.ogg")

        elif task == "transform_clipboard":
            log(
                f'Calling LLM with instruction "{text}" and tasked to transform the clipboard'
            )

            clipboard = str(pyclip.paste())
            if not clipboard:
                notif(log("Clipboard is empty, this is not compatible with the task"))
                raise SystemExit()
            log(f"Clipboard content: '{clipboard}'")

            LLM_response = completion(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompts["transform_clipboard"],
                    },
                    {
                        "role": "user",
                        "content": f"INPUT_TEXT: '{clipboard}'\n\nINSTRUCTION: '{text}'",
                    },
                ],
            )
            answer = LLM_response.json()["choices"][0]["message"]["content"]
            log(f'LLM clipboard transformation: "{answer}"')

            log("Pasting clipboard")
            # pyautogui.click()
            pyclip.copy(answer)
            notif(answer)
            if auto_paste:
                os.system("xdotool key ctrl+v")
                pyclip.copy(clipboard)
                log("Clipboard reset")
            playsound("sounds/Positive.ogg")

        elif "voice_chat" in task:
            if "new" in task:
                voice_file = f"/tmp/quick_whisper_chat_{int(time.time())}.txt"
                log(f"Creating new voice chat file: {voice_file}")

                messages = [
                    {"role": "system", "content": system_prompts["voice"]},
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

                log(f"Reusing previous voice chat file: {voice_file}")

                with open(voice_file, "r") as f:
                    lines = [line.strip() for line in f.readlines()]

                messages = [
                    {"role": "system", "content": system_prompts["voice"]}]
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

            log(f"Calling LLM with messages: '{messages}'")
            LLM_response = completion(model=model, messages=messages)
            answer = LLM_response.json()["choices"][0]["message"]["content"]
            log(f'LLM answer to the chat: "{answer}"')
            notif(answer)

            vocal_file_mp3 = tempfile.NamedTemporaryFile(suffix=".mp3").name
            if voice_engine == "piper":
                try:
                    subprocess.run(
                        [
                            "echo",
                            answer,
                            "|",
                            "python",
                            "-m",
                            "piper",
                            "--model",
                            speaker_models[lang],
                            "--output_file",
                            vocal_file_mp3,
                        ]
                    )

                    log(f"Playing voice file: {vocal_file_mp3}")
                    playsound(vocal_file_mp3)
                except Exception as err:
                    notif(
                        log(f"Error when using piper so will use espeak: '{err}'"))
                    voice_engine = "espeak"

            if voice_engine == "openai":
                try:
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
                    notif(
                        log(f"Error when using openai so will use espeak: '{err}'"))
                    voice_engine = "espeak"

            if voice_engine == "espeak":
                subprocess.run(
                    ["espeak", "-v", lang, "-p", "20", "-s", "110", "-z", answer]
                )

            if voice_engine is None:
                log("voice_engine is None so not speaking.")

            # Add text and answer to the file
            with open(voice_file, "a") as f:
                f.write("\n#####\n")
                f.write(f"{text}\n")
                f.write("\n#####\n")
                f.write(f"{answer}\n")

        log("Done.")


if __name__ == "__main__":
    import fire

    try:
        fire.Fire(QuickWhisper)
    except Exception as err:
        os.system("killall rec")
        notif(f"Error: {err}")
        raise
