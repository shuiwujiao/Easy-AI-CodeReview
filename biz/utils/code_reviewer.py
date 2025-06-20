import abc
import os
import re
from typing import Dict, Any, List

import yaml
from jinja2 import Template

from biz.llm.factory import Factory
from biz.utils.log import logger
from biz.utils.token_util import count_tokens, truncate_text_by_tokens


class BaseReviewer(abc.ABC):
    """代码审查基类"""

    def __init__(self, prompt_key: str):
        self.client = Factory().getClient()
        self.prompts = self._load_prompts(prompt_key, os.getenv("REVIEW_STYLE", "professional"))

    def _load_prompts(self, prompt_key: str, style="professional") -> Dict[str, Any]:
        """加载提示词配置"""
        prompt_templates_file = "conf/prompt_templates.yml"
        try:
            # 在打开 YAML 文件时显式指定编码为 UTF-8，避免使用系统默认的 GBK 编码。
            with open(prompt_templates_file, "r", encoding="utf-8") as file:
                prompts = yaml.safe_load(file).get(prompt_key, {})

                # 使用Jinja2渲染模板
                def render_template(template_str: str) -> str:
                    return Template(template_str).render(style=style)

                system_prompt = render_template(prompts["system_prompt"])
                user_prompt = render_template(prompts["user_prompt"])

                return {
                    "system_message": {"role": "system", "content": system_prompt},
                    "user_message": {"role": "user", "content": user_prompt},
                }
        except (FileNotFoundError, KeyError, yaml.YAMLError) as e:
            logger.error(f"加载提示词配置失败: {e}")
            raise Exception(f"提示词配置加载失败: {e}")

    def call_llm(self, messages: List[Dict[str, Any]]) -> str:
        """调用 LLM 进行代码审核"""
        logger.info(f"向 AI 发送代码 Review 请求, messages: {messages}")
        review_result = self.client.completions(messages=messages)
        logger.info(f"收到 AI 返回结果: {review_result}")
        return review_result

    @abc.abstractmethod
    def review_code(self, *args, **kwargs) -> str:
        """抽象方法，子类必须实现"""
        pass


class CodeReviewer(BaseReviewer):
    """代码 Diff 级别的审查"""

    def __init__(self):
        # 不预加载通用提示词，而是动态加载
        self.client = Factory().getClient()
        # 语言到提示词映射
        self.language_prompts = {
            'python': 'python_review_prompt',
            'javascript': 'javascript_review_prompt',
            'typescript': 'javascript_review_prompt',
            'java': 'java_review_prompt',
            'go': 'go_review_prompt',
            'php': 'php_review_prompt',
            'cpp': 'cpp_review_prompt',
            'c': 'cpp_review_prompt',
            'vue': 'vue3_review_prompt',
            'js': 'javascript_review_prompt',
            'ts': 'javascript_review_prompt',
            'py': 'python_review_prompt',
        }

    def _detect_language_from_diff(self, diffs_text: str) -> str:
        """从diff文本中检测主要编程语言"""
        # 文件扩展名到语言的映射
        file_extensions = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.jsx': 'javascript',
            '.tsx': 'typescript',
            '.vue': 'vue',
            '.java': 'java',
            '.go': 'go',
            '.php': 'php',
            '.cpp': 'cpp',
            '.cc': 'cpp',
            '.cxx': 'cpp',
            '.c': 'c',
            '.h': 'cpp',
            '.hpp': 'cpp',
        }
        
        # 统计各种语言的文件数量
        language_counts = {}
        vue3_indicators = 0
        
        # 尝试多种文件路径模式
        file_patterns = [
            r'^\+\+\+ b/(.+)$',  # Git diff格式: +++ b/file.vue
            r'^\+\+\+ (.+)$',    # 简化格式: +++ file.vue
            r'^--- a/(.+)$',     # Git diff格式: --- a/file.vue
            r'^--- (.+)$',       # 简化格式: --- file.vue
            r'^diff --git a/(.+) b/(.+)$',  # Git diff格式: diff --git a/file.vue b/file.vue
        ]
        
        for line in diffs_text.split('\n'):
            # 尝试所有文件路径模式
            file_path = None
            for pattern in file_patterns:
                match = re.search(pattern, line)
                if match:
                    if pattern == r'^diff --git a/(.+) b/(.+)$':
                        # 对于diff --git格式，取第一个文件路径
                        file_path = match.group(1)
                    else:
                        file_path = match.group(1)
                    break
            
            if file_path:
                # 获取文件扩展名
                ext = os.path.splitext(file_path)[1].lower()
                if ext in file_extensions:
                    lang = file_extensions[ext]
                    language_counts[lang] = language_counts.get(lang, 0) + 1
                    logger.info(f"检测到文件: {file_path}, 扩展名: {ext}, 语言: {lang}")
            
            # 检查代码内容中的Vue3特征
            line_lower = line.lower()
            if any(indicator in line_lower for indicator in [
                'setup()', 'defineprops', 'defineemits', 'ref(', 'reactive(',
                'computed(', 'watch(', 'onmounted', 'onunmounted',
                'composition api', 'script setup', '<script setup'
            ]):
                vue3_indicators += 1
                logger.info(f"检测到Vue3特征: {line.strip()}")
        
        # 如果没有通过文件路径检测到语言，尝试从内容中检测
        if not language_counts:
            # 检查是否包含Vue相关的内容
            if any(indicator in diffs_text.lower() for indicator in [
                '<template>', '<script>', '<style>', 'vue', '.vue'
            ]):
                language_counts['vue'] = 1
                logger.info("通过内容检测到Vue文件")
        
        # 返回出现最多的语言，如果没有检测到则返回默认
        if language_counts:
            primary_language = max(language_counts, key=language_counts.get)
            
            # 如果是Vue且有Vue3特征，记录日志
            if primary_language == 'vue' and vue3_indicators > 0:
                logger.info(f"检测到Vue3代码，Vue3特征数量: {vue3_indicators}")
            elif primary_language == 'vue':
                logger.info(f"检测到Vue文件，但未发现Vue3特征，Vue3特征数量: {vue3_indicators}")
            
            logger.info(f"检测到主要编程语言: {primary_language}")
            return primary_language
        
        logger.info("未检测到特定编程语言，使用通用审查提示词")
        return 'default'

    def _get_appropriate_prompt(self, diffs_text: str) -> str:
        """根据代码内容选择合适的提示词"""
        detected_lang = self._detect_language_from_diff(diffs_text)
        return self.language_prompts.get(detected_lang, 'code_review_prompt')

    def _load_language_specific_prompts(self, prompt_key: str, style="professional") -> Dict[str, Any]:
        """加载语言特定的提示词配置"""
        prompt_templates_file = "conf/prompt_templates.yml"
        try:
            with open(prompt_templates_file, "r", encoding="utf-8") as file:
                prompts = yaml.safe_load(file).get(prompt_key, {})

                def render_template(template_str: str) -> str:
                    return Template(template_str).render(style=style)

                system_prompt = render_template(prompts["system_prompt"])
                user_prompt = render_template(prompts["user_prompt"])

                return {
                    "system_message": {"role": "system", "content": system_prompt},
                    "user_message": {"role": "user", "content": user_prompt},
                }
        except (FileNotFoundError, KeyError, yaml.YAMLError) as e:
            logger.error(f"加载语言特定提示词配置失败: {e}")
            # 如果加载失败，回退到通用提示词
            return self._load_fallback_prompts(style)

    def _load_fallback_prompts(self, style="professional") -> Dict[str, Any]:
        """加载通用提示词作为回退"""
        prompt_templates_file = "conf/prompt_templates.yml"
        try:
            with open(prompt_templates_file, "r", encoding="utf-8") as file:
                prompts = yaml.safe_load(file).get("code_review_prompt", {})

                def render_template(template_str: str) -> str:
                    return Template(template_str).render(style=style)

                system_prompt = render_template(prompts["system_prompt"])
                user_prompt = render_template(prompts["user_prompt"])

                return {
                    "system_message": {"role": "system", "content": system_prompt},
                    "user_message": {"role": "user", "content": user_prompt},
                }
        except (FileNotFoundError, KeyError, yaml.YAMLError) as e:
            logger.error(f"加载通用提示词配置失败: {e}")
            raise Exception(f"提示词配置加载失败: {e}")

    def _convert_changes_to_diff_format(self, changes: list) -> str:
        """将changes列表转换为标准的diff格式"""
        if not changes:
            return ""
        
        diff_content = []
        for change in changes:
            # 处理不同的change格式
            if isinstance(change, dict):
                # GitLab API返回的格式
                if 'diff' in change:
                    diff_text = change['diff']
                    # 如果diff不包含文件路径信息，但有new_path，则添加标准diff头
                    if not diff_text.startswith('diff --git') and 'new_path' in change:
                        diff_text = f"diff --git a/{change['new_path']} b/{change['new_path']}\nindex 0000000..0000000 100644\n--- a/{change['new_path']}\n+++ b/{change['new_path']}\n{diff_text}"
                    diff_content.append(diff_text)
                elif 'new_path' in change and 'old_path' in change:
                    # 构建简单的diff格式
                    diff_content.append(f"diff --git a/{change['old_path']} b/{change['new_path']}")
                    if 'new_file' in change and change['new_file']:
                        diff_content.append(f"new file mode 100644")
                    elif 'deleted_file' in change and change['deleted_file']:
                        diff_content.append(f"deleted file mode 100644")
                    diff_content.append(f"--- a/{change['old_path']}")
                    diff_content.append(f"+++ b/{change['new_path']}")
                    if 'diff' in change:
                        diff_content.append(change['diff'])
            elif isinstance(change, str):
                # 如果已经是字符串格式，直接添加
                diff_content.append(change)
        
        return "\n".join(diff_content)

    def review_and_strip_code(self, changes_text: str, commits_text: str = "") -> str:
        """
        Review判断changes_text超出取前REVIEW_MAX_TOKENS个token，超出则截断changes_text，
        调用review_code方法，返回review_result，如果review_result是markdown格式，则去掉头尾的```
        :param changes_text: 可以是字符串或列表格式的changes
        :param commits_text:
        :return:
        """
        # 如果changes_text是列表格式，转换为diff格式
        if isinstance(changes_text, list):
            changes_text = self._convert_changes_to_diff_format(changes_text)
        elif hasattr(changes_text, '__iter__') and not isinstance(changes_text, str):
            # 处理其他可迭代对象
            changes_text = self._convert_changes_to_diff_format(list(changes_text))
        
        # 如果超长，取前REVIEW_MAX_TOKENS个token
        review_max_tokens = int(os.getenv("REVIEW_MAX_TOKENS", 10000))
        # 如果changes为空,打印日志
        if not changes_text:
            logger.info("代码为空, diffs_text = %", str(changes_text))
            return "代码为空"

        # 计算tokens数量，如果超过REVIEW_MAX_TOKENS，截断changes_text
        tokens_count = count_tokens(changes_text)
        if tokens_count > review_max_tokens:
            changes_text = truncate_text_by_tokens(changes_text, review_max_tokens)

        review_result = self.review_code(changes_text, commits_text).strip()
        if review_result.startswith("```markdown") and review_result.endswith("```"):
            return review_result[11:-3].strip()
        return review_result

    def review_code(self, diffs_text: str, commits_text: str = "") -> str:
        """Review 代码并返回结果"""
        # 智能选择提示词
        prompt_key = self._get_appropriate_prompt(diffs_text)
        style = os.getenv("REVIEW_STYLE", "professional")
        
        logger.info(f"检测到的语言对应的提示词: {prompt_key}")
        logger.info(f"当前审查风格: {style}")
        logger.info(f"可用的语言提示词映射: {self.language_prompts}")
        
        # 加载对应的提示词
        if prompt_key != "code_review_prompt":
            logger.info(f"使用语言特定提示词: {prompt_key}")
            try:
                prompts = self._load_language_specific_prompts(prompt_key, style)
                logger.info(f"成功加载语言特定提示词: {prompt_key}")
            except Exception as e:
                logger.error(f"加载语言特定提示词失败: {e}, 回退到通用提示词")
                prompts = self._load_fallback_prompts(style)
        else:
            logger.info("使用通用提示词: code_review_prompt")
            prompts = self._load_fallback_prompts(style)
        
        # 记录实际使用的提示词内容（前100个字符）
        system_content = prompts["system_message"]["content"]
        logger.info(f"实际使用的system prompt前100字符: {system_content[:100]}...")
        
        messages = [
            prompts["system_message"],
            {
                "role": "user",
                "content": prompts["user_message"]["content"].format(
                    diffs_text=diffs_text, commits_text=commits_text
                ),
            },
        ]
        return self.call_llm(messages)

    @staticmethod
    def parse_review_score(review_text: str) -> int:
        """解析 AI 返回的 Review 结果，返回评分"""
        if not review_text:
            return 0
        match = re.search(r"总分[:：]\s*(\d+)分?", review_text)
        return int(match.group(1)) if match else 0

