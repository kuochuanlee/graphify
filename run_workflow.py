import argparse
import subprocess
import sys
import os

def run_command(cmd, desc):
    print(f"\n[執行中] {desc}...")
    print(f"> {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n[錯誤] {desc} 失敗 (Exit code: {result.returncode})")
        sys.exit(result.returncode)
    print(f"[完成] {desc}")

def main():
    parser = argparse.ArgumentParser(description="Graphify Book 處理流程包裝工具")
    parser.add_argument("book_folder", help="書本資料夾的路徑")
    parser.add_argument("--step", type=int, choices=[1, 2, 3], required=True, 
                        help="執行的階段 (1=偵測與準備, 2=合併與建構, 3=匯出與收尾)")
    
    args = parser.parse_args()
    book_folder = args.book_folder
    out_dir = os.path.join(book_folder, "graphify-out")
    
    # 基本指令前綴
    base_cmd = [sys.executable, "-m", "graphify", "pipeline", "--out-dir", out_dir]

    if args.step == 1:
        print(f"=== 階段 1：偵測與準備 ===")
        run_command(base_cmd + ["detect", "--book", book_folder], "Step 1: detect")
        run_command(base_cmd + ["book-prepare"], "Step 2: book-prepare")
        
        print("\n" + "="*60)
        print("[完成] 階段 1 已完成！")
        print("-> 請「複製以下整段提示詞」，貼到 AI 對話視窗中讓它執行：")
        print("\n------------------ 提示詞開始 ------------------")
        print(f"請幫我執行語意提取（Step 3）。\n")
        print(f"目標書本資料夾為：`{book_folder}`")
        print(f"請讀取 {out_dir}/prompts 這個目錄下的所有 .txt 提示詞。\n")
        print("[注意] 【強制執行規則 - 最高優先級】")
        print("1. [跳過實作計畫] 這是一個明確的例行任務。請直接開始執行提取，絕對不需要建立實作計畫 (Implementation Plan)，也不要問我是否授權或同意。")
        print("2. [不要停下來等我同意] 一次把所有檔案做完！請連續透過循序工具呼叫，把所有的 chunk 一路處理到最後。不要分批處理，也不要中斷並要求我回覆「繼續」。")
        print("3. [遇到細節自動判斷] 請直接一路執行到底。過程中若遇到格式或小錯誤，請自行決定最佳處理方式，不要中斷流程來問我。")
        print("4. 結果請一律儲存回 .json 格式到Chunks目錄。\n")
        print(f"當「所有」提示詞檔案都確實處理完成後，請告訴我目前的進度，並提醒我執行下一階段指令：")
        print(f"  python run_workflow.py \"{book_folder}\" --step 2")
        print("------------------ 提示詞結束 ------------------\n")

    elif args.step == 2:
        print(f"=== 階段 2：合併、建構與分析 ===")
        run_command(base_cmd + ["merge-semantic"], "Step 4: merge-semantic")
        run_command(base_cmd + ["merge-all"], "Step 5: merge-all")
        run_command(base_cmd + ["build", book_folder], "Step 6: build")
        
        print("\n" + "="*60)
        print("[完成] 階段 2 已完成！")
        print("-> 請「複製以下整段提示詞」，貼到 AI 對話視窗中讓它執行：")
        print("\n------------------ 提示詞開始 ------------------")
        print(f"請幫我執行社群命名（Step 7）。\n")
        print(f"目標書本資料夾為：`{book_folder}`\n")
        print("[注意] 【強制執行規則 - 最高優先級】")
        print("1. [跳過實作計畫] 請直接開始執行，絕對不需要寫實作計畫，也不要問我是否同意。")
        print("2. [一路直行到底] 處理過程中請自行判斷中文字詞，不要停下來要求我確認，請一口氣把以下步驟做完。\n")
        print(f"執行步驟：")
        print(f"1. 請讀取 `{out_dir}/.graphify_analysis.json`。")
        print(f"2. 幫裡面的各個社群想出 3~5 個字的繁體中文名稱。")
        print(f"3. 將結果儲存到 `{out_dir}/labels_draft.json`。")
        print(f"4. 直接立刻執行命令套用標籤：")
        print(f"   python -m graphify pipeline --out-dir \"{out_dir}\" label --from-file \"{out_dir}/labels_draft.json\" --path \"{book_folder}\"")
        print("\n所有步驟真正完成後，請提醒我執行最後一階段指令：")
        print(f"  python run_workflow.py \"{book_folder}\" --step 3")
        print("------------------ 提示詞結束 ------------------\n")

    elif args.step == 3:
        print(f"=== 階段 3：匯出與收尾 ===")
        run_command(base_cmd + ["export", "--obsidian", "--wiki"], "Step 8: export")
        run_command(base_cmd + ["finalize", book_folder], "Step 9: finalize")
        
        print("\n" + "="*60)
        print("[完成] 所有流程已順利完成！")
        print(f"你的論證圖譜與相關產出已儲存在 `{out_dir}` 目錄下。")
        print("你可以請 AI 到 GRAPH_REPORT.md 中幫你總結「上帝節點」與「驚喜發現」！")

if __name__ == "__main__":
    main()
