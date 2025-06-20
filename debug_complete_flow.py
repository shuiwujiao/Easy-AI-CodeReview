#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
完整调试代码审查流程
"""

import sys
import os
import re
import yaml
from jinja2 import Template

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def convert_changes_to_diff_format(changes):
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

def detect_language_from_diff(diffs_text):
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
    
    print("=== 开始语言检测 ===")
    print(f"输入的diff文本长度: {len(diffs_text)}")
    print(f"前300字符: {diffs_text[:300]}")
    
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
                print(f"匹配到文件路径: {file_path}")
                break
        
        if file_path:
            # 获取文件扩展名
            ext = os.path.splitext(file_path)[1].lower()
            if ext in file_extensions:
                lang = file_extensions[ext]
                language_counts[lang] = language_counts.get(lang, 0) + 1
                print(f"检测到文件: {file_path}, 扩展名: {ext}, 语言: {lang}")
        
        # 检查代码内容中的Vue3特征
        line_lower = line.lower()
        if any(indicator in line_lower for indicator in [
            'setup()', 'defineprops', 'defineemits', 'ref(', 'reactive(',
            'computed(', 'watch(', 'onmounted', 'onunmounted',
            'composition api', 'script setup', '<script setup'
        ]):
            vue3_indicators += 1
            print(f"检测到Vue3特征: {line.strip()}")
    
    # 如果没有通过文件路径检测到语言，尝试从内容中检测
    if not language_counts:
        # 检查是否包含Vue相关的内容
        if any(indicator in diffs_text.lower() for indicator in [
            '<template>', '<script>', '<style>', 'vue', '.vue'
        ]):
            language_counts['vue'] = 1
            print("通过内容检测到Vue文件")
    
    # 返回出现最多的语言，如果没有检测到则返回默认
    if language_counts:
        primary_language = max(language_counts, key=language_counts.get)
        
        # 如果是Vue且有Vue3特征，记录日志
        if primary_language == 'vue' and vue3_indicators > 0:
            print(f"检测到Vue3代码，Vue3特征数量: {vue3_indicators}")
        elif primary_language == 'vue':
            print(f"检测到Vue文件，但未发现Vue3特征，Vue3特征数量: {vue3_indicators}")
        
        print(f"检测到主要编程语言: {primary_language}")
        return primary_language
    
    print("未检测到特定编程语言，使用通用审查提示词")
    return 'default'

def get_appropriate_prompt(diffs_text):
    """根据代码内容选择合适的提示词"""
    detected_lang = detect_language_from_diff(diffs_text)
    language_prompts = {
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
    return language_prompts.get(detected_lang, 'code_review_prompt')

def load_language_specific_prompts(prompt_key, style="professional"):
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
        print(f"加载语言特定提示词配置失败: {e}")
        return None

def load_fallback_prompts(style="professional"):
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
        print(f"加载通用提示词配置失败: {e}")
        raise Exception(f"提示词配置加载失败: {e}")

def review_and_strip_code(changes_text, commits_text=""):
    """模拟review_and_strip_code方法"""
    print("=== 开始review_and_strip_code ===")
    
    # 如果changes_text是列表格式，转换为diff格式
    if isinstance(changes_text, list):
        print("检测到changes是列表格式，进行转换...")
        changes_text = convert_changes_to_diff_format(changes_text)
    elif hasattr(changes_text, '__iter__') and not isinstance(changes_text, str):
        print("检测到changes是可迭代对象，转换为列表...")
        changes_text = convert_changes_to_diff_format(list(changes_text))
    
    print(f"转换后的changes_text类型: {type(changes_text)}")
    print(f"转换后的changes_text长度: {len(changes_text)}")
    
    # 模拟review_code调用
    return review_code(changes_text, commits_text)

def review_code(diffs_text, commits_text=""):
    """模拟review_code方法"""
    print("=== 开始review_code ===")
    
    # 智能选择提示词
    prompt_key = get_appropriate_prompt(diffs_text)
    style = "professional"
    
    print(f"检测到的语言对应的提示词: {prompt_key}")
    print(f"当前审查风格: {style}")
    
    # 加载对应的提示词
    if prompt_key != "code_review_prompt":
        print(f"使用语言特定提示词: {prompt_key}")
        try:
            prompts = load_language_specific_prompts(prompt_key, style)
            if prompts:
                print(f"成功加载语言特定提示词: {prompt_key}")
            else:
                print("语言特定提示词加载失败，回退到通用提示词")
                prompts = load_fallback_prompts(style)
        except Exception as e:
            print(f"加载语言特定提示词失败: {e}, 回退到通用提示词")
            prompts = load_fallback_prompts(style)
    else:
        print("使用通用提示词: code_review_prompt")
        prompts = load_fallback_prompts(style)
    
    # 记录实际使用的提示词内容（前100个字符）
    system_content = prompts["system_message"]["content"]
    print(f"实际使用的system prompt前100字符: {system_content[:100]}...")
    
    return f"使用提示词: {prompt_key}"

def test_complete_flow():
    """测试完整流程"""
    
    # 模拟GitLab API返回的changes格式
    changes = [
        {
            'diff': '''@@ -1,42 +1,50 @@
-<!-- FaultyCounter.vue -->
+<!-- FaultyTodoList.vue -->
 <template>
     <div>
-      <h2>Counter: {{ count }}</h2>
-      <button @click="incrementCount">Increase</button>
-      <button @click="reset">Reset</button>
+      <h1>My Todos</h1>

-      <p v-if="count = 5">You reached five!</p>
+      <ul>
+        <li v-for="todo in todos" :key="todo.id">
+          <input type="checkbox" v-model="todo.done">
+          <span :style="{ textDecoration: todo.done ? 'line-through' : none }">
+            {{ todo.text }}
+          </span>
+        </li>
+      </ul>

-      <input v-model.number="stepSize" placeholder="Step size" />
+      <input v-model="newTodoText" placeholder="New todo">
+      <button @click="addTodo">Add</button>

-      <p v-if="todos.length = 0">No todos left!</p>
+      <p v-if="todos.length = 0">No todos left!</p>
     </div>
   </template>

   <script setup>
-  import { ref, computed } from 'vue'
+  import { ref } from 'vue'

-  const count = ref(0)
-  let stepSize = 1
+  const todos = [
+    { id: 1, text: 'Learn Vue 3', done: false },
+    { id: 2, text: 'Build a project', done: false }
+  ]

-  function incrementCount() {
-    count += stepSize
-  }
+  let newTodoText = ref('')

-  function reset() {
-    count.value == 0
-  }
+  function addTodo() {
+    if (newTodoText !== '') {
+      todos.push({
+        id: Date.now(),
+        text: newTodoText,
+        done: false
+      })
+      newTodoText = ''
+    }
+  }
-
-  const isEven = computed(() => {
-    return count % 2 === 0
-  })
   </script>

   <style scoped>
-  button {
-    margin-right: 10px
-    background-color: lightblue;
-    border: none;
-    padding: 6px 12px;
-    cursor: pointer;
+  li {
+    list-style: none;
+    margin-bottom: 8px;
   }
   </style>''',
            'new_path': 'src/views/testAi.vue',
            'additions': 33,
            'deletions': 25
        }
    ]
    
    print("=== 测试完整代码审查流程 ===")
    result = review_and_strip_code(changes, "测试提交")
    print(f"\n=== 最终结果 ===")
    print(result)

if __name__ == "__main__":
    test_complete_flow() 