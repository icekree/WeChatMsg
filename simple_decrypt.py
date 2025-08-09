#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
from multiprocessing import freeze_support

from wxManager import Me
from wxManager.decrypt import get_info_v3
from wxManager.decrypt import decrypt_v3


def simple_decrypt():
    """
    简化的解密流程
    """
    print("=== 微信聊天记录解密工具 ===")
    
    # 1. 获取微信信息
    print("1. 获取微信信息...")
    version_list_path = 'wxManager/decrypt/version_list.json'
    
    try:
        with open(version_list_path, "r", encoding="utf-8") as f:
            version_list = json.loads(f.read())
        print("   版本列表加载成功")
    except Exception as e:
        print(f"   错误：无法加载版本列表 - {e}")
        return
    
    # 2. 搜索微信进程
    print("2. 搜索微信进程...")
    try:
        wx_infos = get_info_v3(version_list)
        if not wx_infos:
            print("   未找到微信3.x进程，请确保微信正在运行")
            return
        print(f"   找到 {len(wx_infos)} 个微信实例")
    except Exception as e:
        print(f"   错误：搜索微信进程失败 - {e}")
        return
    
    # 3. 处理每个微信实例
    for i, wx_info in enumerate(wx_infos):
        print(f"\n3. 处理微信实例 {i+1}:")
        print(f"   用户: {wx_info.nick_name}")
        print(f"   微信号: {wx_info.wxid}")
        print(f"   版本: {wx_info.version}")
        print(f"   数据目录: {wx_info.wx_dir}")
        
        if not wx_info.key:
            print("   警告：未获取到解密密钥，跳过")
            continue
        
        print(f"   解密密钥: {wx_info.key[:20]}...")
        
        # 4. 创建输出目录
        output_dir = wx_info.wxid
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"   创建输出目录: {output_dir}")
        
        # 5. 解密数据库
        print("4. 开始解密数据库...")
        try:
            decrypt_v3.decrypt_db_files(wx_info.key, src_dir=wx_info.wx_dir, dest_dir=output_dir)
            print("   数据库解密完成")
        except Exception as e:
            print(f"   错误：解密失败 - {e}")
            continue
        
        # 6. 创建info.json
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
        
        print(f"5. 完成！解密后的数据库位于: {msg_dir}")
        
        # 检查生成的文件
        if os.path.exists(msg_dir):
            files = [f for f in os.listdir(msg_dir) if f.endswith('.db')]
            print(f"   生成的数据库文件: {len(files)} 个")
            for file in files[:5]:  # 显示前5个文件
                print(f"     - {file}")
            if len(files) > 5:
                print(f"     ... 还有 {len(files)-5} 个文件")
        
        print("\n" + "="*50)
        return True
    
    return False


if __name__ == '__main__':
    freeze_support()
    success = simple_decrypt()
    
    if success:
        print("\n解密完成！你现在可以运行以下步骤：")
        print("1. python example/2-contact.py  # 查看联系人")
        print("2. python example/3-exporter.py  # 导出聊天记录")
    else:
        print("\n解密失败，请检查：")
        print("1. 微信是否正在运行")
        print("2. 是否以管理员身份运行此脚本")
        print("3. 微信版本是否支持")