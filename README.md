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

1. 运行main.py，随后在浏览器打开 http://127.0.0.1:7860/  
2. 将待翻译的音视频文件放入input文件夹  
3. 在设置页面的“大模型”和“小模型”处填写你的API密钥、端点链接、使用的模型等  
4. 点击保存设置  
5. 进入主程序页面，点击运行后等待即可  

# 常见问题

### Q1: 安装 requirements.txt 时出错
- **pip 版本过低**：`python -m pip install --upgrade pip`
- **网络问题**：使用国内镜像 `pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`
- **特定包失败**：手动安装失败包

### Q2: 显存不足（CUDA out of memory）
- 在设置页面中使用更小的转录模型，随后点击保存设置

### Q3: 下载模型失败
- 手动下载模型放到指定目录
- 使用代理或切换网络环境