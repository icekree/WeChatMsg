#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
WeChatMsg 超简单Web界面
集成所有核心功能：解密、联系人、导出
"""

import os
import json
import time
import asyncio
from typing import List, Dict, Any
from multiprocessing import freeze_support
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# 导入核心功能模块
from wxManager import DatabaseConnection, MessageType, Me
from wxManager.decrypt import get_info_v3, decrypt_v3
from exporter.config import FileType
from exporter import HtmlExporter, TxtExporter, DocxExporter, MarkdownExporter, ExcelExporter

app = FastAPI(title="WeChatMsg Web UI", description="微信聊天记录工具Web界面")

# 全局变量存储状态
current_db_dir = ""
current_db_version = 3
current_database = None

def fix_contact_attributes(contact):
    """修复联系人属性，确保所有字符串属性都是字符串类型"""
    try:
        # 修复可能是元组或其他类型的属性
        if hasattr(contact, 'remark'):
            remark = getattr(contact, 'remark', '')
            if isinstance(remark, tuple):
                contact.remark = ' '.join(str(x) for x in remark if x)
            elif not isinstance(remark, str):
                contact.remark = str(remark) if remark else ''
        
        if hasattr(contact, 'nickname'):
            nickname = getattr(contact, 'nickname', '')
            if isinstance(nickname, tuple):
                contact.nickname = ' '.join(str(x) for x in nickname if x)
            elif not isinstance(nickname, str):
                contact.nickname = str(nickname) if nickname else ''
        
        if hasattr(contact, 'alias'):
            alias = getattr(contact, 'alias', '')
            if isinstance(alias, tuple):
                contact.alias = ' '.join(str(x) for x in alias if x)
            elif not isinstance(alias, str):
                contact.alias = str(alias) if alias else ''
        
        # 确保有一个可用的显示名称
        if not contact.remark and contact.nickname:
            contact.remark = contact.nickname
        elif not contact.remark and not contact.nickname:
            contact.remark = getattr(contact, 'wxid', 'Unknown')
            
        # 清理文件名中的非法字符
        if hasattr(contact, 'remark') and contact.remark:
            import re
            contact.remark = re.sub(r'[\\/:*?"<>|\r\n]', '_', contact.remark)
            
    except Exception as e:
        print(f"修复联系人属性时出错: {e}")
    
    return contact

@app.get("/", response_class=HTMLResponse)
async def index():
    """主页面"""
    html_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WeChatMsg 工具</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Microsoft YaHei', Arial, sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; background: white; border-radius: 10px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { text-align: center; color: #333; margin-bottom: 30px; }
        .section { margin-bottom: 30px; padding: 20px; border: 1px solid #eee; border-radius: 8px; }
        .section h2 { color: #555; margin-bottom: 15px; }
        button { background: #07c160; color: white; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-size: 14px; margin: 5px; }
        button:hover { background: #06ad56; }
        button:disabled { background: #ccc; cursor: not-allowed; }
        .status { margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 4px; min-height: 50px; }
        .success { background: #d4edda; color: #155724; }
        .error { background: #f8d7da; color: #721c24; }
        .warning { background: #fff3cd; color: #856404; }
        select, input { padding: 8px; margin: 5px; border: 1px solid #ddd; border-radius: 4px; }
        .contact-list { max-height: 200px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; }
        .contact-item { padding: 5px; cursor: pointer; border-bottom: 1px solid #eee; }
        .contact-item:hover { background: #f0f0f0; }
        .contact-item.selected { background: #e3f2fd; }
        .flex { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .log { background: #000; color: #0f0; padding: 15px; border-radius: 4px; font-family: monospace; max-height: 300px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔥 WeChatMsg 聊天记录工具</h1>
        
        <!-- 第一步：解密微信数据 -->
        <div class="section">
            <h2>📱 第一步：解密微信数据</h2>
            <div class="flex">
                <button onclick="decryptWechat()">🔓 检测并解密微信数据</button>
                <button onclick="refreshStatus()">🔄 刷新状态</button>
            </div>
            <div id="decrypt-status" class="status">请先确保微信正在运行，然后点击解密按钮</div>
        </div>

        <!-- 第二步：查看联系人 -->
        <div class="section">
            <h2>👥 第二步：查看联系人</h2>
            <div class="flex">
                <button onclick="loadContacts()" id="load-contacts-btn" disabled>📋 加载联系人列表</button>
                <span>数据库状态: <span id="db-status">未连接</span></span>
            </div>
            <div id="contacts-list" class="contact-list" style="display:none;"></div>
            <div id="contact-status" class="status"></div>
        </div>

        <!-- 第三步：导出聊天记录 -->
        <div class="section">
            <h2>💾 第三步：导出聊天记录</h2>
            <div class="flex">
                <select id="export-format">
                    <option value="html">HTML格式</option>
                    <option value="txt">TXT格式</option>
                    <option value="docx">Word文档</option>
                    <option value="markdown">Markdown格式</option>
                    <option value="xlsx">Excel格式</option>
                </select>
                <input type="text" id="selected-contact" placeholder="选择的联系人" readonly>
                <button onclick="exportChat()" id="export-btn" disabled>📤 导出聊天记录</button>
                <button onclick="exportAllContacts()" id="export-all-btn" disabled>📦 批量导出全部</button>
            </div>
            <div id="export-status" class="status"></div>
        </div>

        <!-- 操作日志 -->
        <div class="section">
            <h2>📊 操作日志</h2>
            <div id="log" class="log">等待操作...</div>
        </div>
    </div>

    <script>
        let contacts = [];
        let selectedContact = null;

        function log(message) {
            const logDiv = document.getElementById('log');
            const timestamp = new Date().toLocaleTimeString();
            logDiv.innerHTML += `[${timestamp}] ${message}\\n`;
            logDiv.scrollTop = logDiv.scrollHeight;
        }

        async function decryptWechat() {
            const statusDiv = document.getElementById('decrypt-status');
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '🔄 解密中...';
            
            statusDiv.className = 'status warning';
            statusDiv.textContent = '正在检测微信进程并解密数据库...';
            log('开始解密微信数据...');

            try {
                const response = await fetch('/api/decrypt', { method: 'POST' });
                const result = await response.json();
                
                if (result.success) {
                    statusDiv.className = 'status success';
                    statusDiv.innerHTML = `✅ 解密成功！<br>用户: ${result.data.nickname}<br>微信号: ${result.data.wxid}<br>数据库: ${result.data.db_path}`;
                    document.getElementById('load-contacts-btn').disabled = false;
                    document.getElementById('db-status').textContent = '已连接';
                    log(`解密成功: ${result.data.nickname} (${result.data.wxid})`);
                } else {
                    throw new Error(result.error);
                }
            } catch (error) {
                statusDiv.className = 'status error';
                statusDiv.textContent = `❌ 解密失败: ${error.message}`;
                log(`解密失败: ${error.message}`);
            }

            btn.disabled = false;
            btn.textContent = '🔓 检测并解密微信数据';
        }

        async function loadContacts() {
            const statusDiv = document.getElementById('contact-status');
            const btn = document.getElementById('load-contacts-btn');
            const listDiv = document.getElementById('contacts-list');
            
            btn.disabled = true;
            btn.textContent = '🔄 加载中...';
            statusDiv.className = 'status warning';
            statusDiv.textContent = '正在加载联系人列表...';
            log('开始加载联系人...');

            try {
                const response = await fetch('/api/contacts');
                const result = await response.json();
                
                if (result.success) {
                    contacts = result.data;
                    displayContacts(contacts);
                    listDiv.style.display = 'block';
                    statusDiv.className = 'status success';
                    statusDiv.textContent = `✅ 已加载 ${contacts.length} 个联系人`;
                    log(`加载联系人成功: ${contacts.length} 个`);
                } else {
                    throw new Error(result.error);
                }
            } catch (error) {
                statusDiv.className = 'status error';
                statusDiv.textContent = `❌ 加载失败: ${error.message}`;
                log(`加载联系人失败: ${error.message}`);
            }

            btn.disabled = false;
            btn.textContent = '📋 加载联系人列表';
        }

        function displayContacts(contactList) {
            const listDiv = document.getElementById('contacts-list');
            listDiv.innerHTML = contactList.map((contact, index) => 
                `<div class="contact-item" onclick="selectContact(${index})" data-index="${index}">
                    ${contact.is_chatroom ? '👥' : '👤'} ${contact.nickname} (${contact.wxid})
                </div>`
            ).join('');
        }

        function selectContact(index) {
            selectedContact = contacts[index];
            document.querySelectorAll('.contact-item').forEach(item => item.classList.remove('selected'));
            document.querySelector(`[data-index="${index}"]`).classList.add('selected');
            document.getElementById('selected-contact').value = selectedContact.nickname;
            document.getElementById('export-btn').disabled = false;
            document.getElementById('export-all-btn').disabled = false;
            log(`选择联系人: ${selectedContact.nickname}`);
        }

        async function exportChat() {
            if (!selectedContact) {
                alert('请先选择一个联系人');
                return;
            }

            const format = document.getElementById('export-format').value;
            const statusDiv = document.getElementById('export-status');
            const btn = document.getElementById('export-btn');
            
            btn.disabled = true;
            btn.textContent = '📤 导出中...';
            statusDiv.className = 'status warning';
            statusDiv.textContent = `正在导出 ${selectedContact.nickname} 的聊天记录为 ${format.toUpperCase()} 格式...`;
            log(`开始导出: ${selectedContact.nickname} -> ${format}`);

            try {
                const response = await fetch('/api/export', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        wxid: selectedContact.wxid,
                        format: format,
                        batch: false
                    })
                });
                const result = await response.json();
                
                if (result.success) {
                    statusDiv.className = 'status success';
                    statusDiv.innerHTML = `✅ 导出成功！<br>文件保存在: ${result.data.output_path}<br>耗时: ${result.data.duration}s`;
                    log(`导出成功: ${result.data.output_path} (${result.data.duration}s)`);
                } else {
                    throw new Error(result.error);
                }
            } catch (error) {
                statusDiv.className = 'status error';
                statusDiv.textContent = `❌ 导出失败: ${error.message}`;
                log(`导出失败: ${error.message}`);
            }

            btn.disabled = false;
            btn.textContent = '📤 导出聊天记录';
        }

        async function exportAllContacts() {
            if (contacts.length === 0) {
                alert('请先加载联系人列表');
                return;
            }

            const format = document.getElementById('export-format').value;
            const statusDiv = document.getElementById('export-status');
            const btn = document.getElementById('export-all-btn');
            
            if (!confirm(`确定要批量导出所有 ${contacts.length} 个联系人的聊天记录吗？这可能需要很长时间。`)) {
                return;
            }
            
            btn.disabled = true;
            btn.textContent = '📦 批量导出中...';
            statusDiv.className = 'status warning';
            statusDiv.textContent = `正在批量导出所有联系人的聊天记录为 ${format.toUpperCase()} 格式...`;
            log(`开始批量导出: ${contacts.length} 个联系人 -> ${format}`);

            try {
                const response = await fetch('/api/export', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        format: format,
                        batch: true
                    })
                });
                const result = await response.json();
                
                if (result.success) {
                    statusDiv.className = 'status success';
                    statusDiv.innerHTML = `✅ 批量导出成功！<br>导出了 ${result.data.count} 个联系人<br>文件保存在: ${result.data.output_path}<br>总耗时: ${result.data.duration}s`;
                    log(`批量导出成功: ${result.data.count} 个联系人 (${result.data.duration}s)`);
                } else {
                    throw new Error(result.error);
                }
            } catch (error) {
                statusDiv.className = 'status error';
                statusDiv.textContent = `❌ 批量导出失败: ${error.message}`;
                log(`批量导出失败: ${error.message}`);
            }

            btn.disabled = false;
            btn.textContent = '📦 批量导出全部';
        }

        function refreshStatus() {
            log('刷新状态...');
            // 可以添加状态检查逻辑
        }

        // 页面加载完成
        document.addEventListener('DOMContentLoaded', function() {
            log('WeChatMsg Web UI 已启动');
            log('请按顺序操作：1.解密数据 -> 2.加载联系人 -> 3.导出记录');
        });
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

@app.post("/api/decrypt")
async def decrypt_wechat():
    """解密微信数据API"""
    global current_db_dir, current_db_version, current_database
    
    try:
        # 加载版本列表
        version_list_path = 'wxManager/decrypt/version_list.json'
        with open(version_list_path, "r", encoding="utf-8") as f:
            version_list = json.loads(f.read())
        
        # 获取微信信息
        wx_infos = get_info_v3(version_list)
        if not wx_infos:
            raise Exception("未找到微信3.x进程，请确保微信正在运行")
        
        wx_info = wx_infos[0]  # 取第一个微信实例
        
        if not wx_info.key:
            raise Exception("未获取到解密密钥")
        
        # 创建输出目录
        output_dir = wx_info.wxid
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 解密数据库
        decrypt_v3.decrypt_db_files(wx_info.key, src_dir=wx_info.wx_dir, dest_dir=output_dir)
        
        # 创建info.json
        msg_dir = os.path.join(output_dir, 'Msg')
        if not os.path.exists(msg_dir):
            os.makedirs(msg_dir)
        
        me = Me()
        me.wx_dir = wx_info.wx_dir
        me.wxid = wx_info.wxid
        me.name = wx_info.nick_name
        
        info_path = os.path.join(msg_dir, 'info.json')
        with open(info_path, 'w', encoding='utf-8') as f:
            json.dump(me.to_json(), f, ensure_ascii=False, indent=4)
        
        # 更新全局变量
        current_db_dir = msg_dir
        current_db_version = 3
        
        return JSONResponse({
            "success": True,
            "data": {
                "nickname": wx_info.nick_name,
                "wxid": wx_info.wxid,
                "version": wx_info.version,
                "db_path": msg_dir
            }
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        })

@app.get("/api/contacts")
async def get_contacts():
    """获取联系人列表API"""
    global current_db_dir, current_db_version, current_database
    
    try:
        if not current_db_dir:
            raise Exception("请先解密微信数据")
        
        # 创建数据库连接
        conn = DatabaseConnection(current_db_dir, current_db_version)
        current_database = conn.get_interface()
        
        if not current_database:
            raise Exception("数据库连接失败")
        
        # 获取联系人
        contacts = current_database.get_contacts()
        
        contact_list = []
        for i, contact in enumerate(contacts):
            try:
                # 安全地获取属性，避免方法和None值
                wxid = getattr(contact, 'wxid', '') or ''
                nickname = getattr(contact, 'nickname', '') or getattr(contact, 'remark', '') or wxid
                
                # is_chatroom 是一个方法，需要调用
                is_chatroom = False
                try:
                    if hasattr(contact, 'is_chatroom') and callable(getattr(contact, 'is_chatroom')):
                        is_chatroom = contact.is_chatroom()
                    else:
                        is_chatroom = getattr(contact, 'is_chatroom', False)
                except:
                    is_chatroom = False
                
                # 确保所有值都是可序列化的
                contact_data = {
                    "wxid": str(wxid),
                    "nickname": str(nickname),
                    "is_chatroom": bool(is_chatroom)
                }
                contact_list.append(contact_data)
                
            except Exception as e:
                print(f"处理联系人 {i} 时出错: {e}")
                # 跳过有问题的联系人，继续处理下一个
                continue
        
        return JSONResponse({
            "success": True,
            "data": contact_list
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        })

@app.post("/api/export")
async def export_chat(request: Request):
    """导出聊天记录API"""
    global current_database
    
    try:
        data = await request.json()
        format_type = data.get('format', 'html')
        is_batch = data.get('batch', False)
        
        if not current_database:
            raise Exception("请先加载联系人列表")
        
        # 创建输出目录
        output_dir = './exported_data/'
        os.makedirs(output_dir, exist_ok=True)
        
        start_time = time.time()
        
        # 格式映射
        format_map = {
            'html': (HtmlExporter, FileType.HTML),
            'txt': (TxtExporter, FileType.TXT),
            'docx': (DocxExporter, FileType.DOCX),
            'markdown': (MarkdownExporter, FileType.MARKDOWN),
            'xlsx': (ExcelExporter, FileType.XLSX)
        }
        
        if format_type not in format_map:
            raise Exception(f"不支持的导出格式: {format_type}")
        
        exporter_class, file_type = format_map[format_type]
        
        if is_batch:
            # 批量导出
            contacts = current_database.get_contacts()
            count = 0
            for contact in contacts:
                try:
                    # 修复联系人属性，确保都是字符串
                    contact = fix_contact_attributes(contact)
                    exporter = exporter_class(
                        current_database,
                        contact,
                        output_dir=output_dir,
                        type_=file_type,
                        message_types=None,
                        time_range=['2020-01-01 00:00:00', '2035-03-12 00:00:00'],
                        group_members=None
                    )
                    exporter.start()
                    count += 1
                except Exception as e:
                    print(f"批量导出联系人 {getattr(contact, 'wxid', 'unknown')} 失败: {e}")
                    continue  # 跳过失败的联系人
            
            duration = time.time() - start_time
            return JSONResponse({
                "success": True,
                "data": {
                    "count": count,
                    "output_path": output_dir,
                    "duration": round(duration, 2)
                }
            })
        else:
            # 单个导出
            wxid = data.get('wxid')
            if not wxid:
                raise Exception("请指定要导出的联系人")
            
            contact = current_database.get_contact_by_username(wxid)
            if not contact:
                raise Exception(f"未找到联系人: {wxid}")
            
            # 修复联系人属性，确保都是字符串
            contact = fix_contact_attributes(contact)
            
            exporter = exporter_class(
                current_database,
                contact,
                output_dir=output_dir,
                type_=file_type,
                message_types=None,
                time_range=['2020-01-01 00:00:00', '2035-03-12 00:00:00'],
                group_members=None
            )
            exporter.start()
            
            duration = time.time() - start_time
            return JSONResponse({
                "success": True,
                "data": {
                    "output_path": output_dir,
                    "duration": round(duration, 2)
                }
            })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        })

if __name__ == "__main__":
    freeze_support()
    print("🚀 启动 WeChatMsg Web UI...")
    print("📱 请确保微信正在运行")
    print("🌐 浏览器访问: http://localhost:8888")
    print("⚠️  首次使用请以管理员权限运行")
    
    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="info")