# Group Information

Yan LIU     50026858  
Haowen YAN  50027498  
Qixian DENG 50026236  

# Statements

**This source code is solely for the purpose of authorized course assignment grading.**  

**Any other usages, including but not limited to copying, sharing, distributing, or posting online, are strictly prohibited.**

# How To Use

We would recommend using Windows.

### Step 1: Install FFMPEG

Download the official static version of the build (https://ffmpeg.org/download.html). 
After decompression, add its bin directory to the system environment variable PATH.

## Step 2: Install Requirements

```cmd
pip install -r requirements.txt
```

This way it will defaultly install torch, torchaudio, faiss in CPU version.

**We recommend installing your own "torch" and "torchaudio" that suits your GPU resources before installing the requirements.**

### Step 3: Input

Put the audio or video into "./input" folder, and add your short description into "description.txt" if needed.

The description can be used as the initial prompt of stt, also additional information for LLM translation and refining.

### Step 3: Run

```cmd
python main.py
```

After the process, you will get the result in "./output" folder.

# Evaluation

The evaluation scripts are in "./Testing"

To run the test:

Go to the main folder, run:

```cmd
python ./Testing/eval.py
python ./Testing/tool_d.py
```

# Tool Specifications

The agent can call tools including:

1. Full text database  
(see ./Tools/Database.py)
2. Vector database  
(see ./Tools/VectorDatabase.py)
3. Web crawler for searching  
(see ./Tools/Crawler.py)

The agent prioritizes using databases instead of using Internet information.

# Settings

Refer to "./settings.json"

