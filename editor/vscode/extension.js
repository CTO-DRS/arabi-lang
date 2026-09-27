// -*- coding: utf-8 -*-
// امتداد لغة عربي — عميل خادم اللغة (LSP).
// يتطلب حزمة vscode-languageclient لتشغيل الخادم؛ إن لم تتوفر
// يعمل الامتداد بلا خادم (التلوين والمقتطفات فقط) بلا أخطاء.

'use strict';

const vscode = require('vscode');
const vscodeRetry = () => {
    try {
        return require('vscode-languageclient/node');
    } catch (_e) {
        return null;
    }
};

const languageclient = vscodeRetry();

let client = null;
let serverEnabled = null; // آخر حالة معروفة للإعداد

// عنوان إشعارات الحالة أسفل النافذة
function inform(message, kind) {
    const status = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Left, 10);
    status.text = `$(code) عربي: ${message}`;
    status.tooltip = 'خادم لغة عربي';
    status.show();
    setTimeout(() => status.dispose(), 6000);
    if (kind) {
        // أنواع الرسائل: 1 معلومات، 2 تحذير، 3 خطأ
        vscode.window.showInformationMessage(message);
    }
}

function buildServerOptions(context) {
    const config = vscode.workspace.getConfiguration('arabi');
    const pythonPath = config.get('languageServer.pythonPath') || 'python3';
    let serverPath = config.get('languageServer.serverPath') || '';
    if (!serverPath) {
        // الافتراضي: مجلد لغة عربي بجوار مساحة العمل إن وُجد
        const workspaceFolders = vscode.workspace.workspaceFolders || [];
        const candidates = [
            vscode.Uri.joinPath(workspaceFolders[0]?.uri, 'arabi.py'),
            vscode.Uri.file(`${context.extensionPath}/../../arabi.py`),
        ];
        serverPath = ''; // يحدد عند التشغيل أدناه
        for (const candidate of candidates) {
            if (candidate && candidate.fsPath) {
                const dir = candidate.fsPath.replace(/[/\\]arabi\.py$/, '');
                try {
                    require('fs').accessSync(candidate.fsPath);
                    serverPath = dir;
                    break;
                } catch (_e) { /* نحاول التالي */ }
            }
        }
    }
    return { pythonPath, serverPath };
}

function startServer(context) {
    if (!languageclient) {
        inform('الحزمة vscode-languageclient غير مثبتة — التلوين والمقتطفات فقط');
        return;
    }
    const config = vscode.workspace.getConfiguration('arabi');
    if (config.get('languageServer.enabled') === false) {
        return;
    }
    if (client) {
        return; // يعمل بالفعل
    }

    const { pythonPath, serverPath } = buildServerOptions(context);
    if (!serverPath) {
        inform('لم يُعثر على arabi.py — حدد arabi.languageServer.serverPath');
        return;
    }

    const serverOptions = {
        command: pythonPath,
        args: ['arabi.py', '--لغة'],
        options: { cwd: serverPath },
    };

    const clientOptions = {
        documentSelector: [{ language: 'arabi', scheme: 'file' }],
        synchronize: {
            configurationSection: 'arabi',
        },
        outputChannelName: 'لغة عربي — خادم اللغة',
    };

    client = new languageclient.LanguageClient(
        'arabiLanguageServer',
        'خادم لغة عربي',
        serverOptions,
        clientOptions
    );

    client.start();
    serverEnabled = true;
    inform('خادم اللغة يعمل — تشخيص وإكمال ذكي للملفات .عربي');
}

async function stopServer() {
    if (client) {
        await client.stop();
        client = null;
        serverEnabled = false;
        inform('خادم اللغة توقف');
    }
}

function activate(context) {
    context.subscriptions.push(
        vscode.commands.registerCommand('arabi.restartServer', async () => {
            await stopServer();
            startServer(context);
        }),
        vscode.commands.registerCommand('arabi.toggleServer', async () => {
            if (client) {
                await stopServer();
            } else {
                startServer(context);
            }
        }),
        vscode.workspace.onDidChangeConfiguration((event) => {
            if (event.affectsConfiguration('arabi.languageServer')) {
                vscode.commands.executeCommand('arabi.restartServer');
            }
        })
    );

    // إطلاق الخادم عند فتح أول ملف .عربي أو فورًا إن كان ملفًا مفتوحًا
    if (vscode.workspace.textDocuments.some(
            (doc) => doc.languageId === 'arabi')) {
        startServer(context);
    } else {
        const watcher = vscode.workspace.createFileSystemWatcher('**/*.عربي');
        const launchOnce = () => {
            startServer(context);
        };
        context.subscriptions.push(watcher);
        watcher.onDidCreate(launchOnce);
    }
}

function deactivate() {
    return stopServer();
}

module.exports = {
    activate,
    deactivate,
};
