-- 初始化 DaVinci Resolve API
resolve = Resolve()
ui = fu.UIManager
disp = bmd.UIDispatcher(ui)

-- 用于存储日志信息的局部变量
logMessages = ""

-- 创建窗口（删除了“匹配文件名前”、“SpinBox”、“位”、以及“FullMatchCheckBox”相关UI）
win = disp:AddWindow({
    ID = "ReplaceWindow",
    WindowTitle = "批量替换片段-完全匹配",
    Geometry = {700, 300, 400, 400},  -- 定义窗口大小
    ui:VGroup{
        Weight = 1,
        ui:HGroup{
            Weight = 0.2,
            ui:LineEdit{ ID = "FolderPath", Text = "", Weight = 0.7 },  -- 文件夹路径输入框
            ui:Button{ ID = "OpenFolderButton", Text = "打开文件夹" , Weight = 0.3},  -- 打开文件夹按钮
        },
        -- 已删除与 fullMatch / matchLength 相关的 UI 行
        ui:HGroup{
            Weight = 0.2,
            ui:Button{ ID = "CheckButton", Text = "检查文件", Weight = 0.12 },   -- 检查按钮
            ui:Button{ ID = "StartReplaceButton", Text = "开始替换" ,Weight = 0.13},  -- 开始替换按钮
        },
        ui:TextEdit{ ID = "LogOutput", ReadOnly = true, Weight = 3, Text = "" },  -- 显示日志信息的文本框
        ui:Button {
            ID = 'OpenLinkButton',
            Text = 'Copyright by HB',
            Alignment = { AlignHCenter = true, AlignVCenter = true },
            Font = ui:Font {
                PixelSize = 12,
                StyleName = 'Bold'
            },
            Flat = true,  
            TextColor = {0.1, 0.3, 0.9, 1},  
            BackgroundColor = {1, 1, 1, 0},  
            Weight = 0.1
        },
    }
})

-- 打印日志到TextEdit控件
function logMessage(message)
    local logBox = win:GetItems().LogOutput
    logMessages = logMessages .. message .. "\n"
    logBox.Text = logMessages
end

-- 文件夹选择函数
function openFolderDialog()
    folder = fu:RequestDir()
    if folder then
        win:GetItems().FolderPath.Text = folder
    end
end

--[[
  由于我们已经删除了 FullMatchCheckBox，所以在后续逻辑里，
  直接把 fullMatch 设置为 true，保证始终采用“完整文件名匹配 + 递归子文件夹”。
]]
local fullMatch = true

-- 获取替换文件夹中的文件
function getFilesInFolder(folderPath)
    local t, popen = {}, io.popen
    local command
    local isWindows = package.config:sub(1,1) == "\\"
    -- 此处简化：因为 fullMatch 固定为 true，所以始终走递归子文件夹命令
    if isWindows then
        command = 'dir /b /s "' .. folderPath .. '"'
    else
        command = 'find "' .. folderPath .. '" -type f'
    end

    local pfile = popen(command)
    if not pfile then
        logMessage("无法打开替换文件夹: " .. folderPath)
        return t
    end

    for line in pfile:lines() do
        local filepath = line
        if isWindows then
            filepath = filepath:gsub("\\", "/")  -- 统一使用 '/'
        end
        local filename = filepath:match("([^/\\]+)$")  -- 提取文件名
        
        local nameWithoutExtension = filename:match("(.+)%..+$")
        if nameWithoutExtension then
            -- fullMatch 为 true 时，直接以 “文件名去后缀” 作为 matchKey
            local matchKey = nameWithoutExtension
            t[matchKey] = filepath
        end
    end

    pfile:close()
    return t
end

-- 获取媒体池中的素材列表
function getClipsFromMediaPool()
    local projectManager = resolve:GetProjectManager()
    local project = projectManager:GetCurrentProject()
    local mediaPool = project:GetMediaPool()
    local current_folder = mediaPool:GetCurrentFolder()

    -- fullMatch = true 时，递归获取所有子文件夹素材
    return getAllClipsFromMediaPoolFolder(current_folder)
end

-- 递归获取媒体池中的所有素材
function getAllClipsFromMediaPoolFolder(folder)
    local clips = {}
    local current_clips = folder:GetClipList()
    for _, clip in ipairs(current_clips) do
        table.insert(clips, clip)
    end
    local subfolders = folder:GetSubFolders()
    for _, subfolder in pairs(subfolders) do
        local subfolder_clips = getAllClipsFromMediaPoolFolder(subfolder)
        for _, clip in ipairs(subfolder_clips) do
            table.insert(clips, clip)
        end
    end
    return clips
end

-- 处理素材的通用函数
function processClips(clips, a_files, processClipFunc)
    if not clips or #clips == 0 then
        logMessage("当前媒体池中没有任何文件。")
        return
    end

    -- 按照素材名称排序
    table.sort(clips, function(a, b)
        return a:GetName() < b:GetName()
    end)

    -- 遍历素材并处理
    for i, clip in ipairs(clips) do
        local clip_name = clip:GetName()
        local nameWithoutExtension = clip_name:match("(.+)%..+$")
        
        if not nameWithoutExtension then
            -- 没有后缀名的特殊情况
            processClipFunc(clip, nil, nil)
        else
            local matchKey = nameWithoutExtension  -- fullMatch 情况
            -- fullMatch 时，直接使用 entire nameWithoutExtension 作为键
            if a_files[matchKey] then
                processClipFunc(clip, matchKey, a_files[matchKey])
            else
                processClipFunc(clip, nil, nil)
            end
        end
    end
end

-- 执行检查函数
function checkFiles()
    -- 清空日志
    logMessages = ""
    win:GetItems().LogOutput.Text = ""

    -- 获取用户输入
    local folderPath = win:GetItems().FolderPath.Text
    if folderPath == "" then
        logMessage("请选择一个文件夹。")
        return
    end

    -- 获取替换文件夹中的文件
    local a_files = getFilesInFolder(folderPath)
    if not next(a_files) then
        logMessage("替换文件夹中没有找到任何文件。")
        return
    end

    -- 获取媒体池中的素材（包含子文件夹）
    local clips = getClipsFromMediaPool()
    if not clips then return end

    -- 初始化匹配的文件名键列表
    local matchKeys = {}

    -- 定义处理每个素材的函数
    function checkClip(clip, matchKey, new_clip_path)
        if matchKey then
            if not matchKeys[matchKey] then
                matchKeys[matchKey] = true
            end
        end
    end

    -- 处理素材
    processClips(clips, a_files, checkClip)

    -- 如果没有找到可替换的文件
    if next(matchKeys) == nil then
        logMessage("未找到任何可替换的文件。")
        return
    end

    -- 打印替换路径
    logMessage("替换路径: " .. folderPath)

    -- 收集并排序匹配的文件名
    local sortedMatchKeys = {}
    for key, _ in pairs(matchKeys) do
        table.insert(sortedMatchKeys, key)
    end
    table.sort(sortedMatchKeys)

    -- 打印匹配的文件名
    logMessage("匹配完整文件名（去后缀）：")
    logMessage(table.concat(sortedMatchKeys, "\n"))

    -- 打印匹配的文件数量
    logMessage("找到媒体池中可替换文件数量: " .. #sortedMatchKeys)
end

-- 执行替换函数
function startReplace()
    -- 清空日志
    logMessages = ""
    win:GetItems().LogOutput.Text = ""

    -- 获取用户输入
    local folderPath = win:GetItems().FolderPath.Text
    if folderPath == "" then
        logMessage("请选择一个文件夹。")
        return
    end

    -- 获取替换文件夹中的文件
    local a_files = getFilesInFolder(folderPath)
    if not next(a_files) then
        logMessage("替换文件夹中没有找到任何文件。")
        return
    end

    -- 获取媒体池中的素材
    local clips = getClipsFromMediaPool()
    if not clips then return end

    -- 初始化日志列表和计数器
    local successLogs = {}
    local notFoundLogs = {}
    local invalidNameLogs = {}
    local totalClips = 0  -- 可替换的素材数量
    local replacedCount = 0

    -- 首先统计可替换的素材数量
    local matchClips = {}
    function countReplaceableClips(clip, matchKey, new_clip_path)
        if matchKey then
            totalClips = totalClips + 1
            table.insert(matchClips, {clip = clip, matchKey = matchKey, new_clip_path = new_clip_path})
        end
    end

    -- 遍历素材，统计可替换的素材
    processClips(clips, a_files, countReplaceableClips)

    -- 如果没有可替换的素材，提示并退出
    if totalClips == 0 then
        logMessage("未找到任何可替换的文件。")
        return
    end

    -- 显示初始进度
    logMessages = "开始替换：0/" .. totalClips
    win:GetItems().LogOutput.Text = logMessages

    -- 定义处理每个素材的函数
    function replaceClip(clipData)
        local clip = clipData.clip
        local matchKey = clipData.matchKey
        local new_clip_path = clipData.new_clip_path
        local original_clip_name = clip:GetName()

        local result = clip:ReplaceClip(new_clip_path)
        if result then
            local new_clip_name = new_clip_path:match("([^/\\]+)$")
            replacedCount = replacedCount + 1
            logMessages = "开始替换：" .. replacedCount .. "/" .. totalClips
            win:GetItems().LogOutput.Text = logMessages
            -- 记录成功日志
            table.insert(successLogs, {filename = original_clip_name, message = "替换素材: " .. original_clip_name .. " ---> " .. new_clip_name})
        else
            table.insert(notFoundLogs, {filename = original_clip_name, message = "替换失败: " .. original_clip_name})
        end
    end

    -- 开始替换
    for _, clipData in ipairs(matchClips) do
        replaceClip(clipData)
    end

    -- 替换完成后，清除进度显示
    logMessages = ""
    win:GetItems().LogOutput.Text = logMessages

    -- 按照文件名排序日志
    table.sort(successLogs, function(a, b)
        return a.filename < b.filename
    end)
    table.sort(notFoundLogs, function(a, b)
        return a.filename < b.filename
    end)
    table.sort(invalidNameLogs, function(a, b)
        return a.filename < b.filename
    end)

    -- 打印成功日志
    if #successLogs > 0 then
        for _, log in ipairs(successLogs) do
            logMessage(log.message)
        end
    end

    -- 打印未找到匹配的文件日志
    if #notFoundLogs > 0 then
        for _, log in ipairs(notFoundLogs) do
            logMessage(log.message)
        end
    end

    -- 打印文件名无效的日志
    if #invalidNameLogs > 0 then
        for _, log in ipairs(invalidNameLogs) do
            logMessage(log.message)
        end
    end
end

-- 绑定按钮事件
win.On.OpenFolderButton.Clicked = openFolderDialog
win.On.StartReplaceButton.Clicked = startReplace
win.On.CheckButton.Clicked = checkFiles

-- 关闭窗口函数
function win.On.ReplaceWindow.Close(ev)
    disp:ExitLoop()
end

-- 打开链接按钮事件
function win.On.OpenLinkButton.Clicked(ev)
    bmd.openurl("https://www.yuque.com/heiba-3jzd7/hk6o2e/rv2fqrqcay0rxpvm")
end

-- 显示窗口
win:Show()
disp:RunLoop()
win:Hide()