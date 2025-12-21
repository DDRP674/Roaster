# 介绍

该项目（“烤肉机”）是一个简易的音视频翻译器，适用于单说话人、无较大噪音和背景音的场景。输入音视频，其将通过STT、LLM、RAG等技术进行翻译和润色，输出简体中文字幕。

# License

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![LICENSE](https://img.shields.io/badge/license-Anti%20996-blue.svg)](https://github.com/996icu/996.ICU/blob/master/LICENSE)
[![996.icu](https://img.shields.io/badge/link-996.icu-red.svg)](https://996.icu)

# 详细安装教程

## 第一步：安装CUDA

如果您的设备支持CUDA（如NVIDIA显卡等），可以先考虑安装CUDA。  
如果已安装或不打算使用GPU可以跳过第一步。  
  
在cmd输入以下命令以检查：
```cmd
nvidia-smi
```
找到“CUDA Version”，其后数字为最高支持的CUDA版本。如果没有显示相应信息，则您的设备很可能不支持CUDA。  
随后，进入网址：https://developer.nvidia.com/cuda-11-8-0-download-archive  
根据自己的操作系统（如Windows 10）选择相应的安装包，下载后双击安装包进行安装。  
这里默认安装CUDA 11.8，如果需要其他版本可以在此寻找：https://developer.nvidia.com/cuda-toolkit-archive  
  
安装完毕后，可以通过以下命令检查是否成功：
```cmd
nvcc --version
```
如果显示版本信息则成功。

## 第二步：安装Python

如果已安装可以跳过这一步。  
在此下载安装包以安装Python：https://www.python.org/downloads/  
建议安装3.10版本。  
注意：在安装过程中一定要勾选 Add python.exe to PATH

## 第三步：安装pytorch

如果已经安装，可以跳过此步。
  
如果使用CUDA 11.8和Windows操作系统，可以直接运行以下命令进行安装：  
```cmd
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```
  
如果希望使用其他CUDA版本，可以进入此网址：https://pytorch.org/get-started/locally/  
选择相应CUDA版本和操作系统后其会自动生成安装命令。  
注意，一定要安装torchaudio  
  
如果不使用GPU，可直接运行以下命令：  
```cmd
pip install torch torchvision torchaudio
```
  
这一过程可能会因网络问题失败，重试即可。

## 第四步：安装FFMPEG

如果已经安装，可以跳过此步。  
  
进入此网址，下载对应您的操作系统的版本的FFMPEG完整安装包：https://ffmpeg.org/download.html  
Windows系统可直接进入Windows builds from gyan.dev，选择ffmpeg-release-full.7z并下载。  
解压后将其解压在一个固定的文件夹中，随后找到其中的bin文件夹，复制这个文件夹目录的地址。  
右键"此电脑" → 属性 → 高级系统设置  
环境变量 → 系统变量 → Path → 编辑  
添加您先前复制的相应的地址即可。

在cmd运行以下命令以检查是否成功安装：
```cmd
ffmpeg -version
```
如果显示版本信息则成功。

## 第五步：安装本项目依赖

在github页面通过 code -> Download ZIP 下载源码。如果安装了git，也可以通过以下命令下载：
```bash
git clone https://github.com/DDRP674/Roaster.git
```
  
解压后进入主目录，在此目录打开命令行，运行：
```cmd
pip install -r requirements.txt
```

## 第六步：配置大语言模型API

在相关云服务网站或从自己搭建的大语言模型获取API地址和密钥，  
填入进 settings.json 的 llms -> SmallModel, LargeModel, LargeModelJson 三栏  
注意：建议使用支持 "response_format": {"type": "json_object"} 的API服务。如果无法获取此类服务，可直接删掉 settings.json 的 llms -> LargeModelJson -> response_format 这一行以及上一行末尾的逗号。

# 使用教程

将音视频文件放入 input 文件夹。如果需要提供有关翻译内容的额外提示信息，可以直接加入进 input/description.txt 文件（这一提示建议尽量简短）。  
随后在主目录运行以下命令：
```cmd
python main.py
```
初次使用可能需要下载模型，请耐心等待。如果因网络问题下载失败，可直接重试。

# 关于设置

settings.json 存放了烤肉机相关配置选项，这里仅做部分介绍。
  
"enable_refine" : true/false 是否开启润色（默认关闭）。润色将消耗更多token，同时有时反而会导致翻译质量下降。  
  
"chunk_size": 一个整数（例如50） 这个选项决定了单次调用大语言模型时同时处理的句子数量。它将影响翻译速度。
  
"Crawler": 存放了与网络爬虫有关的配置，默认关闭。它可以通过网络搜索获取内容以辅助翻译，但其实没什么用。  
  
"search_local": true/false 决定是否启用历史翻译内容查询。默认关闭。在大规模翻译任务（长音视频、多集音视频）中可能有效。
  
"global_memory": true/false 是否在不同视频中共享历史翻译内容。默认开启。如果开启了"search_local"并且不同音视频文件之间没有关联时，可以改为false。
  
"stts": 存放了字幕转录相关模块的配置。  
— "engine": "whisper"/"stable_whisper" 所使用的转录服务。建议使用"stable_whisper"。  
— "model": 所使用的模型。一般medium效果足够。如果显存不足可尝试base/small等模型。  

"llms": 存放了与大语言模型API相关的配置。

# 常见问题

### Q1: 安装 requirements.txt 时出错
- **pip 版本过低**：`python -m pip install --upgrade pip`
- **网络问题**：使用国内镜像 `pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`
- **特定包失败**：手动安装失败包

### Q2: 显存不足（CUDA out of memory）
- 在 settings.json 中将 model 改为 "base" 或 "small"

### Q3: 下载模型失败
- 手动下载模型放到指定目录
- 使用代理或切换网络环境