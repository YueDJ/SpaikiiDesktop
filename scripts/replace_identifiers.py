#!/usr/bin/env python3
"""
代码标识符替换脚本 - 处理函数名、类名、接口名等
"""

import os
import re
import sys
import io

# 设置标准输出编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 排除的目录
EXCLUDE_DIRS = {
    '.git', '.venv-sparkii', 'node_modules', '__pycache__', '.qoder',
    'sparkii_agent.egg-info', 'sparkii_agent.egg-info', '.plans',
    'test-results', 'playwright-report', 'coverage', 'dist', 'build',
    '.next', '.nuxt', '.output', '.cache', '.temp', '.tmp',
}

# 排除的路径模式
EXCLUDE_PATHS = {
    '.git',
    'node_modules',
}

# 代码标识符替换映射
IDENTIFIER_REPLACEMENTS = [
    # 函数名替换
    (r'buildSparkiiWebSocketUrl', 'buildSparkiiWebSocketUrl'),
    (r'SparkiiPlugin', 'SparkiiPlugin'),
    (r'SparkiiPluginSDK', 'SparkiiPluginSDK'),
    (r'SparkiiConsoleModal', 'SparkiiConsoleModal'),
    (r'SparkiiConsoleModalProps', 'SparkiiConsoleModalProps'),
    (r'SparkiiCLI', 'SparkiiCLI'),
    (r'SparkiiMCPOAuthProvider', 'SparkiiMCPOAuthProvider'),
    (r'SparkiiTokenStorage', 'SparkiiTokenStorage'),
    (r'SparkiiIndexSource', 'SparkiiIndexSource'),
    (r'SparkiiSkin', 'SparkiiSkin'),
    
    # 类名替换
    (r'SparkiiConfigWriteProtection', 'SparkiiConfigWriteProtection'),
    (r'SparkiiUidGid', 'SparkiiUidGid'),
    (r'ChownToSparkiiUid', 'ChownToSparkiiUid'),
    (r'GetSparkiiHome', 'GetSparkiiHome'),
    (r'SparkiiBinDirOnPath', 'SparkiiBinDirOnPath'),
    (r'SparkiiInternalDynamicSecrets', 'SparkiiInternalDynamicSecrets'),
    (r'SystemUnitSparkiiHome', 'SystemUnitSparkiiHome'),
    (r'SystemUnitRefreshSyncsSparkiiHome', 'SystemUnitRefreshSyncsSparkiiHome'),
    (r'SparkiiHomeForTargetUser', 'SparkiiHomeForTargetUser'),
    (r'LegacySparkiiUnitDetection', 'LegacySparkiiUnitDetection'),
    (r'RemoveLegacySparkiiUnits', 'RemoveLegacySparkiiUnits'),
    
    # 测试类名替换
    (r'TestSparkiiConfigWriteProtection', 'TestSparkiiConfigWriteProtection'),
    (r'TestResolveSparkiiUidGid', 'TestResolveSparkiiUidGid'),
    (r'TestChownToSparkiiUid', 'TestChownToSparkiiUid'),
    (r'TestGetSparkiiHome', 'TestGetSparkiiHome'),
    (r'TestSparkiiTokenStorage', 'TestSparkiiTokenStorage'),
    (r'TestSparkiiBinDirOnPath', 'TestSparkiiBinDirOnPath'),
    (r'TestSparkiiInternalDynamicSecrets', 'TestSparkiiInternalDynamicSecrets'),
    (r'TestSystemUnitSparkiiHome', 'TestSystemUnitSparkiiHome'),
    (r'TestSystemUnitRefreshSyncsSparkiiHome', 'TestSystemUnitRefreshSyncsSparkiiHome'),
    (r'TestSparkiiHomeForTargetUser', 'TestSparkiiHomeForTargetUser'),
    (r'TestLegacySparkiiUnitDetection', 'TestLegacySparkiiUnitDetection'),
    (r'TestRemoveLegacySparkiiUnits', 'TestRemoveLegacySparkiiUnits'),
    
    # 接口名替换
    (r'SparkiiPlugin', 'SparkiiPlugin'),
    (r'SparkiiPluginSDK', 'SparkiiPluginSDK'),
    (r'SparkiiConsoleModalProps', 'SparkiiConsoleModalProps'),
    
    # 变量名替换（如果需要）
    # (r'sparkii_home', 'sparkii_home'),
    # (r'sparkii_config', 'sparkii_config'),
]

# 文件扩展名白名单
FILE_EXTENSIONS = {
    '.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.yaml', '.yml', 
    '.md', '.txt', '.sh', '.bat', '.ps1', '.cfg', '.ini', '.toml',
    '.env', '.env.example', '.dockerignore', '.gitignore', '.gitattributes',
    '.prettierrc', '.prettierignore', '.npmrc', '.nvmrc', '.python-version',
    '.flake8', '.pylintrc', '.eslintrc', '.eslintrc.js', '.eslintrc.json',
    '.eslintrc.yml', '.eslintrc.yaml', '.babelrc', '.babelrc.js',
    '.babelrc.json', '.babelrc.yml', '.babelrc.yaml', '.postcssrc',
    '.postcssrc.js', '.postcssrc.json', '.postcssrc.yml', '.postcssrc.yaml',
    '.stylelintrc', '.stylelintrc.js', '.stylelintrc.json', '.stylelintrc.yml',
    '.stylelintrc.yaml', '.editorconfig', '.pre-commit-config.yaml',
    '.pre-commit-config.yml', '.github', '.gitlab-ci.yml', '.travis.yml',
    '.circleci', '.circleci/config.yml', '.github/workflows', '.github/dependabot.yml',
    '.github/ISSUE_TEMPLATE', '.github/PULL_REQUEST_TEMPLATE.md',
}

def should_process_file(file_path):
    """判断是否应该处理该文件"""
    # 检查文件扩展名
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in FILE_EXTENSIONS:
        return False
    
    # 检查是否在排除目录中
    parts = file_path.split(os.sep)
    for part in parts:
        if part in EXCLUDE_DIRS:
            return False
    
    return True

def replace_identifiers_in_file(file_path, dry_run=False):
    """替换文件中的代码标识符"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"读取文件失败 {file_path}: {e}")
        return False
    
    original_content = content
    
    # 应用替换规则
    for pattern, replacement in IDENTIFIER_REPLACEMENTS:
        content = re.sub(pattern, replacement, content)
    
    # 如果内容有变化
    if content != original_content:
        if dry_run:
            print(f"[DRY RUN] 会修改标识符: {file_path}")
            return True
        else:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"已修改标识符: {file_path}")
                return True
            except Exception as e:
                print(f"写入文件失败 {file_path}: {e}")
                return False
    else:
        return False

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='替换代码标识符')
    parser.add_argument('--dry-run', action='store_true', help='试运行，不实际修改文件')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    args = parser.parse_args()
    
    # 获取当前目录
    current_dir = os.getcwd()
    print(f"扫描目录: {current_dir}")
    
    modified_count = 0
    total_count = 0
    
    # 遍历所有文件
    for root, dirs, files in os.walk(current_dir):
        # 跳过排除目录
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        # 跳过排除路径
        rel_root = os.path.relpath(root, current_dir)
        if any(rel_root.startswith(exclude) for exclude in EXCLUDE_PATHS):
            continue
        
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, current_dir)
            
            if should_process_file(rel_path):
                total_count += 1
                if replace_identifiers_in_file(file_path, dry_run=args.dry_run):
                    modified_count += 1
                    if args.verbose:
                        print(f"  修改了标识符: {rel_path}")
    
    print(f"\n扫描完成:")
    print(f"  总文件数: {total_count}")
    print(f"  修改文件数: {modified_count}")
    
    if args.dry_run:
        print("\n[DRY RUN] 未实际修改任何文件")

if __name__ == "__main__":
    main()