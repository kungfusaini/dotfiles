"use strict";
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = void 0;
const vscode = require("vscode");
const constants_1 = require("./constants");
function isPrimitive(value) {
    return Object(value) !== value;
}
function notice(message) {
    vscode.window.showInformationMessage(message);
}
function getExtensionOptions() {
    return __awaiter(this, void 0, void 0, function* () {
        const pickedIndent = yield vscode.window.showQuickPick(["2", "4"], {
            title: 'Please choose indent.',
        });
        if (!pickedIndent) {
            notice('User aborted.');
            return;
        }
        const pickedPrimitiveTypeSolution = yield vscode.window.showQuickPick(["keep", "parse"], {
            title: 'How to deal with primitive types?',
        });
        if (!pickedPrimitiveTypeSolution) {
            notice('User aborted.');
            return;
        }
        return {
            indent: pickedIndent,
            primitiveType: pickedPrimitiveTypeSolution,
        };
    });
}
function goTop(editor) {
    const startOfDocument = editor.selection.active.with(0, 0);
    editor.revealRange(editor.selection = new vscode.Selection(startOfDocument, startOfDocument), vscode.TextEditorRevealType.AtTop);
}
function handleRegisterCommand(editor) {
    return __awaiter(this, void 0, void 0, function* () {
        const userConfiguration = vscode.workspace.getConfiguration();
        const extensionOptions = (this === null || this === void 0 ? void 0 : this.skipPickers) ? Object.assign(Object.assign({}, constants_1.DEFAULT_OPTIONS), { indent: userConfiguration.get('json.indent'), primitiveType: userConfiguration.get('json.primitiveType') }) : yield getExtensionOptions();
        if (!extensionOptions) {
            return;
        }
        const { indent, primitiveType } = extensionOptions;
        const { document, selection, document: { lineCount: maxLineNumber } } = editor;
        const text = document.getText(selection.isEmpty ? undefined : selection);
        let result = text;
        try {
            result = JSON.stringify(JSON.parse(text, (key, value) => {
                try {
                    const result = JSON.parse(value);
                    if (!isPrimitive(result) || primitiveType === "parse") {
                        return result;
                    }
                    return value;
                }
                catch (e) {
                    return value;
                }
            }), undefined, +indent);
        }
        catch (e) {
            notice('Invalid JSON, Please Check Manually.');
            return;
        }
        const replaced = yield vscode.window.activeTextEditor.edit(editBuilder => {
            editBuilder.replace(new vscode.Range(document.lineAt(0).range.start, document.lineAt(maxLineNumber - 1).range.end), result);
        });
        if (!replaced) {
            notice('Error not related to extension occurs.');
            return;
        }
        goTop(editor);
        notice('Done.');
        if (document.isUntitled) {
            vscode.languages.setTextDocumentLanguage(document, 'json');
            return;
        }
        document.save();
    });
}
function activate(context) {
    return __awaiter(this, void 0, void 0, function* () {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            return;
        }
        const { commands } = vscode;
        const edit = new Promise(resolve => editor.edit(edit => resolve(edit)));
        context.subscriptions.push(commands.registerCommand('json', handleRegisterCommand.bind(null, editor, edit)), commands.registerTextEditorCommand('json.shortcut', handleRegisterCommand.bind({
            skipPickers: true,
        })));
    });
}
exports.activate = activate;
