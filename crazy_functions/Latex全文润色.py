from comm_tools.toolbox import update_ui, trimmed_format_exc, promote_file_to_downloadzone, get_log_folder
from comm_tools.toolbox import CatchException, report_execption, write_history_to_file, zip_folder


class PaperFileGroup():
    def __init__(self):
        self.file_paths = []
        self.file_contents = []
        self.sp_file_contents = []
        self.sp_file_index = []
        self.sp_file_tag = []

        # count_token
        from request_llm.bridge_all import model_info
        enc = model_info["gpt-3.5-turbo"]['tokenizer']
        def get_token_num(txt): return len(enc.encode(txt, disallowed_special=()))
        self.get_token_num = get_token_num

    def run_file_split(self, max_token_limit=1900):
        """
        将长文本分离开来
        """
        for index, file_content in enumerate(self.file_contents):
            if self.get_token_num(file_content) < max_token_limit:
                self.sp_file_contents.append(file_content)
                self.sp_file_index.append(index)
                self.sp_file_tag.append(self.file_paths[index])
            else:
                from .crazy_utils import breakdown_txt_to_satisfy_token_limit_for_pdf
                segments = breakdown_txt_to_satisfy_token_limit_for_pdf(file_content, self.get_token_num, max_token_limit)
                for j, segment in enumerate(segments):
                    self.sp_file_contents.append(segment)
                    self.sp_file_index.append(index)
                    self.sp_file_tag.append(self.file_paths[index] + f".part-{j}.tex")

        print('Segmentation: done')
    def merge_result(self):
        self.file_result = ["" for _ in range(len(self.file_paths))]
        for r, k in zip(self.sp_file_result, self.sp_file_index):
            self.file_result[k] += r

    def write_result(self):
        manifest = []
        for path, res in zip(self.file_paths, self.file_result):
            with open(path + '.polish.tex', 'w', encoding='utf8') as f:
                manifest.append(path + '.polish.tex')
                f.write(res)
        return manifest
    
    def zip_result(self):
        import os, time
        folder = os.path.dirname(self.file_paths[0])
        t = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
        zip_folder(folder, get_log_folder(), f'{t}-polished.zip')


def 多文件润色(file_manifest, project_folder, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, language='en', mode='polish'):
    import time, os, re
    from .crazy_utils import request_gpt_model_multi_threads_with_very_awesome_ui_and_high_efficiency


    #  <-------- 读取Latex文件，删除其中的所有注释 ----------> 
    pfg = PaperFileGroup()

    for index, fp in enumerate(file_manifest):
        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
            file_content = f.read()
            # 定义注释的正则表达式
            comment_pattern = r'(?<!\\)%.*'
            # 使用正则表达式查找注释，并替换为空字符串
            clean_tex_content = re.sub(comment_pattern, '', file_content)
            # 记录删除注释后的文本
            pfg.file_paths.append(fp)
            pfg.file_contents.append(clean_tex_content)

    #  <-------- 拆分过长的latex文件 ----------> 
    pfg.run_file_split(max_token_limit=1024)
    n_split = len(pfg.sp_file_contents)


    #  <-------- 多线程润色开始 ----------> 
    if language == 'en':
        if mode == 'polish':
            inputs_array = ["Below is a section from an academic paper, polish this section to meet the academic standard, " + 
                            "improve the grammar, clarity and overall readability, do not modify any latex command such as \section, \cite and equations:" + 
                            f"\n\n{frag}" for frag in pfg.sp_file_contents]
        else:
            inputs_array = [r"Below is a section from an academic paper, proofread this section." + 
                            r"Do not modify any latex command such as \section, \cite, \begin, \item and equations. " + 
                            r"Answer me only with the revised text:" + 
                        f"\n\n{frag}" for frag in pfg.sp_file_contents]
        inputs_show_user_array = [f"Polish {f}" for f in pfg.sp_file_tag]
        sys_prompt_array = ["You are a professional academic paper writer." for _ in range(n_split)]
    elif language == 'zh':
        if mode == 'polish':
            inputs_array = [f"以下是一篇学术论文中的一段内容，请将此部分润色以满足学术标准，提高语法、清晰度和整体可读性，不要修改任何LaTeX命令，例如\section，\cite和方程式：" + 
                            f"\n\n{frag}" for frag in pfg.sp_file_contents]
        else:
            inputs_array = [f"以下是一篇学术论文中的一段内容，请对这部分内容进行语法矫正。不要修改任何LaTeX命令，例如\section，\cite和方程式：" + 
                            f"\n\n{frag}" for frag in pfg.sp_file_contents] 
        inputs_show_user_array = [f"润色 {f}" for f in pfg.sp_file_tag]
        sys_prompt_array=["你是一位专业的中文学术论文作家。" for _ in range(n_split)]


    gpt_response_collection = yield from request_gpt_model_multi_threads_with_very_awesome_ui_and_high_efficiency(
        inputs_array=inputs_array,
        inputs_show_user_array=inputs_show_user_array,
        llm_kwargs=llm_kwargs,
        chatbot=chatbot,
        history_array=[[""] for _ in range(n_split)],
        sys_prompt_array=sys_prompt_array,
        # max_workers=5,  # 并行任务数量限制，最多同时执行5个，其他的排队等待
        scroller_max_len = 80
    )

    #  <-------- 文本碎片重组为完整的tex文件，整理结果为压缩包 ----------> 
    try:
        pfg.sp_file_result = []
        for i_say, gpt_say in zip(gpt_response_collection[0::2], gpt_response_collection[1::2]):
            pfg.sp_file_result.append(gpt_say)
        pfg.merge_result()
        pfg.write_result()
        pfg.zip_result()
    except:
        print(trimmed_format_exc())

    #  <-------- 整理结果，退出 ----------> 
    create_report_file_name = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime()) + f"-chatgpt.polish.md"
    res = write_history_to_file(gpt_response_collection, file_basename=create_report_file_name)
    promote_file_to_downloadzone(res, chatbot=chatbot)

    history = gpt_response_collection
    chatbot.append((f"{fp}完成了吗？", res))
    yield from update_ui(chatbot=chatbot, history=history) # 刷新界面


@CatchException
def Latex英文润色(txt, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, web_port):
    # 基本信息：功能、贡献者
    chatbot.append([
        "函数插件功能？",
        "对整个Latex项目进行润色。函数插件贡献者: Binary-Husky。（注意，此插件不调用Latex，如果有Latex环境，请使用“Latex英文纠错+高亮”插件）"])
    yield from update_ui(chatbot=chatbot, history=history) # 刷新界面

    # 尝试导入依赖，如果缺少依赖，则给出安装建议
    try:
        import tiktoken
    except:
        report_execption(chatbot, history,
                         a=f"解析项目: {txt}",
                         b=f"导入软件依赖失败。使用该模块需要额外依赖，安装方法```pip install --upgrade tiktoken```。")
        yield from update_ui(chatbot=chatbot, history=history) # 刷新界面
        return
    history = []    # 清空历史，以免输入溢出
    import glob, os
    if os.path.exists(txt):
        project_folder = txt
    else:
        if txt == "": txt = '空空如也的输入栏'
        report_execption(chatbot, history, a = f"解析项目: {txt}", b = f"找不到本地项目或无权访问: {txt}")
        yield from update_ui(chatbot=chatbot, history=history) # 刷新界面
        return
    file_manifest = [f for f in glob.glob(f'{project_folder}/**/*.tex', recursive=True)]
    if len(file_manifest) == 0:
        report_execption(chatbot, history, a = f"解析项目: {txt}", b = f"找不到任何.tex文件: {txt}")
        yield from update_ui(chatbot=chatbot, history=history) # 刷新界面
        return
    yield from 多文件润色(file_manifest, project_folder, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, language='en')






@CatchException
def Latex中文润色(txt, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, web_port):
    # 基本信息：功能、贡献者
    chatbot.append([
        "函数插件功能？",
        "对整个Latex项目进行润色。函数插件贡献者: Binary-Husky"])
    yield from update_ui(chatbot=chatbot, history=history) # 刷新界面

    # 尝试导入依赖，如果缺少依赖，则给出安装建议
    try:
        import tiktoken
    except:
        report_execption(chatbot, history,
                         a=f"解析项目: {txt}",
                         b=f"导入软件依赖失败。使用该模块需要额外依赖，安装方法```pip install --upgrade tiktoken```。")
        yield from update_ui(chatbot=chatbot, history=history) # 刷新界面
        return
    history = []    # 清空历史，以免输入溢出
    import glob, os
    if os.path.exists(txt):
        project_folder = txt
    else:
        if txt == "": txt = '空空如也的输入栏'
        report_execption(chatbot, history, a = f"解析项目: {txt}", b = f"找不到本地项目或无权访问: {txt}")
        yield from update_ui(chatbot=chatbot, history=history) # 刷新界面
        return
    file_manifest = [f for f in glob.glob(f'{project_folder}/**/*.tex', recursive=True)]
    if len(file_manifest) == 0:
        report_execption(chatbot, history, a = f"解析项目: {txt}", b = f"找不到任何.tex文件: {txt}")
        yield from update_ui(chatbot=chatbot, history=history) # 刷新界面
        return
    yield from 多文件润色(file_manifest, project_folder, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, language='zh')




@CatchException
def Latex英文纠错(txt, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, web_port):
    # 基本信息：功能、贡献者
    chatbot.append([
        "函数插件功能？",
        "对整个Latex项目进行纠错。函数插件贡献者: Binary-Husky"])
    yield from update_ui(chatbot=chatbot, history=history) # 刷新界面

    # 尝试导入依赖，如果缺少依赖，则给出安装建议
    try:
        import tiktoken
    except:
        report_execption(chatbot, history,
                         a=f"解析项目: {txt}",
                         b=f"导入软件依赖失败。使用该模块需要额外依赖，安装方法```pip install --upgrade tiktoken```。")
        yield from update_ui(chatbot=chatbot, history=history) # 刷新界面
        return
    history = []    # 清空历史，以免输入溢出
    import glob, os
    if os.path.exists(txt):
        project_folder = txt
    else:
        if txt == "": txt = '空空如也的输入栏'
        report_execption(chatbot, history, a = f"解析项目: {txt}", b = f"找不到本地项目或无权访问: {txt}")
        yield from update_ui(chatbot=chatbot, history=history) # 刷新界面
        return
    file_manifest = [f for f in glob.glob(f'{project_folder}/**/*.tex', recursive=True)]
    if len(file_manifest) == 0:
        report_execption(chatbot, history, a = f"解析项目: {txt}", b = f"找不到任何.tex文件: {txt}")
        yield from update_ui(chatbot=chatbot, history=history) # 刷新界面
        return
    yield from 多文件润色(file_manifest, project_folder, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, language='en', mode='proofread')



