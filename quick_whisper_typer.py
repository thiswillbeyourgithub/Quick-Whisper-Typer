from playsound import playsound
import tempfile
import os
import subprocess
import time

import fire
import pyperclip3
import PySimpleGUI as sg
import openai
from pathlib import Path

# Set up variables and prompts
prompts = {
    "fr": "Dictee voicee sur mon telephone: ",
    "en": "Dictation on my smartphone: "
}
system_prompts = {
    "voice": "You are a helpful assistant. I am in a hurry and your answers will be played on speaker so use as few words as you can while remaining helpful and truthful. Don't use too short sentences otherwise the speakers will crash.",
    "transform_clipboard": "You transform INPUT_TEXT according to an instruction. Only reply the transformed text without anything else."
}
speaker_models = {
    "fr": "fr_FR-gilles-low",
    "en": "en_US-lessac-medium"
}

# Load OpenAI api key from file
openai.api_key = open("API_KEY.txt", "r").read().strip()

def log(message):
    print(message)
    with open("texts.log", "a") as f:
        f.write(f"{int(time.time())} {message}\n")

def popup(prompt, task, lang):
    title = "Sound Recorder"
    text = f"TASK: {task}\nLANG: {lang}"

    layout = [
        [sg.Text(text)],
        [sg.Text("Whisper prompt"), sg.Input(prompt)],
        [sg.Text("ChatGPT instruction"), sg.Input()],
        [sg.Button("Go!", key="-GO-", button_color="red"), sg.Button("Cancel", key="-CANCEL-", button_color="blue")]
    ]

    window = sg.Window(title, layout, keep_on_top=True)
    event, values = window.read()
    window.close()

    if event == "-GO-":
        whisper_prompt = values[0]
        chatgpt_instruction = values[1]
        log(f"Whisper prompt: {whisper_prompt} for task {task}")
        return whisper_prompt, chatgpt_instruction
    else:
        log("Pressed cancel or escape. Exiting.")
        raise SystemExit()

def main(
        lang,
        task,
        voice_engine="espeak",
        prompt=None,
        **kwargs,
        ):
    """
    Parameters
    ----------
    lang
        fr, en
    task
        transform_clipboard, write, voice_chat
    voice_engine
        piper, openai, espeak
    prompt
        default to None
    """
    print("in")
    # Checking if the language is supplied and correct
    allowed_langs = ("fr", "en")
    assert lang != "" and lang in allowed_langs, (
        f"Invalid lang {lang} not part of {allowed_langs}")

    # Checking voice engine
    allowed_voice_engine = ("openai", "piper", "espeak")
    assert "voice" not in task or voice_engine in allowed_voice_engine, (
        f"Invalid voice engine {voice_engine} not part of {allowed_voice_engine}")

    # Selecting prompt based on language
    if not prompt:
        prompt = prompts[lang]
    
    # Checking that the task is allowed
    allowed_tasks = ("transform_clipboard", "voice_chat", "write")
    assert task != "" and task in allowed_tasks, f"Invalid task {task} not part of {allowed_tasks}"

    log(f"Will use language {lang} and prompt {prompt} and task {task}")

    file = tempfile.NamedTemporaryFile(suffix='.mp3').name
    min_duration = 2  # if the recording is shorter, exit

    # Kill any previously running recordings
    start_time = time.time()
    subprocess.run(["killall", "rec"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Start recording
    log(f"Recording {file}")
    subprocess.Popen(f"rec -r 44000 -c 1 -b 16 {file} &", shell=True)

    # Show recording form
    whisper_prompt, chatgpt_instruction = popup(prompt, task, lang)

    # Kill the recording
    subprocess.run(["killall", "rec"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end_time = time.time()
    log(f"Done recording {file}")

    # Check duration
    duration = end_time - start_time
    log(f"Duration {duration}")
    if duration < min_duration:
        log(f"Recording too short ({duration} s), exiting without calling whisper.")
        raise SystemExit()
    
    # Call whisper
    log("Calling whisper")
    with open(file, "rb") as f:
        transcript_response = openai.Audio.transcribe(
                model="whisper-1",
                file=f,
                language=lang,
                prompt=whisper_prompt,
                temperature=0)
    text = transcript_response["text"]
    log(f"Whisper transcript: {text}")

    if task == "write":
        clipboard = pyperclip3.paste()
        if not clipboard:
            log("Clipboard is empty, this is not compatible with the task")
            raise SystemExit()
        log(f"Clipboard content: '{clipboard}'")

        log("Pasting clipboard")
        pyperclip3.copy(text)
        os.system("xdotool key ctrl+v")
        pyperclip3.copy(clipboard)
        log("Clipboard reset")
        return

    elif task == "transform_clipboard":
        log(f"Calling ChatGPT with instruction \"{text}\" and tasked to transform the clipboard")

        clipboard = str(pyperclip3.paste())
        if not clipboard:
            log("Clipboard is empty, this is not compatible with the task")
            raise SystemExit()
        log(f"Clipboard content: '{clipboard}'")

        chatgpt_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo-1106",
            messages=[
                {"role": "system", "content": system_prompts["transform_clipboard"]},
                {"role": "user", "content": f"INPUT_TEXT: '{clipboard}'\n\nINSTRUCTION: '{text}'"}
            ]
        )
        answer = chatgpt_response["choices"][0]["message"]["content"]
        log(f"ChatGPT clipboard transformation: \"{answer}\"")

        log("Pasting clipboard")
        pyperclip3.copy(answer)
        os.system("xdotool key ctrl+v")
        pyperclip3.copy(clipboard)
        log("Clipboard reset")
        return

    elif task == "voice_chat":
        if "new" in kwargs:
            voice_file = f"/tmp/quick_whisper_chat_{int(time.time())}.txt"
            log(f"Creating new voice chat file: {voice_file}")

            messages = [
                    {"role": "system", "content": system_prompts["voice"]},
                    ]

        elif "continue" in kwargs:
            voice_files = [f for f in Path("/tmp").iterdir() if f.name.startswith("quick_whisper_chat_")]
            voice_files = sorted(voice_files, key=lambda x: x.stat().st_ctime)
            voice_file = voice_files[-1]

            log(f"Reusing previous voice chat file: {voice_file}")

            with open(voice_file, "r") as f:
                lines = [line.strip() for line in f.readlines()]

            messages = [{"role": "system", "content": system_prompts["voice"]}]
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
            raise ValueError(kwargs)


        messages.append({"role": "user", "content": text})

        log(f"Calling ChatGPT with messages: '{messages}'")
        chatgpt_response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo-1106",
                messages=messages)
        answer = chatgpt_response["choices"][0]["message"]["content"]
        log(f"ChatGPT answer to the chat: \"{answer}\"")

        vocal_file_mp3 = tempfile.NamedTemporaryFile(suffix='.mp3').name

        if voice_engine == "espeak":
            subprocess.run(
                    ["espeak", "-v", lang, answer])
        elif voice_engine == "piper":
            subprocess.run(
                    ["echo", answer, "|", "python", "-m", "piper", "--model", speaker_models[lang], "--output_file", vocal_file_mp3])

            log(f"Playing voice file: {vocal_file_mp3}")
            playsound(vocal_file_mp3)
        else:
            raise NotImplementedError()

        # Add text and answer to the file
        with open(voice_file, "a") as f:
            f.write("\n#####\n")
            f.write(f"{text}\n")
            f.write("\n#####\n")
            f.write(f"{answer}\n")
        return

if __name__ == "__main__":
    fire.Fire(main)
