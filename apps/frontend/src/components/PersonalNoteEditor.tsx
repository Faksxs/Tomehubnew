import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Bold, Heading1, Heading2, Italic, List, ListOrdered, CheckSquare, Underline as UnderlineIcon, Quote, Table2, Rows3, Columns3, Trash2, Palette, Eraser } from 'lucide-react';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import Placeholder from '@tiptap/extension-placeholder';
import Color from '@tiptap/extension-color';
import { TextStyle } from '@tiptap/extension-text-style';
import { Table } from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableHeader from '@tiptap/extension-table-header';
import TableCell from '@tiptap/extension-table-cell';
import { toPersonalNotePreviewHtml } from '../lib/personalNoteRender';

type SlashCommandType = 'template';

interface SlashItem {
  id: string;
  label: string;
}

interface PersonalNoteEditorProps {
  value: string;
  onChange: (next: string) => void;
  autoFocus?: boolean;
  placeholder?: string;
  minHeight?: number;
  onSlashCommand?: (payload: { command: SlashCommandType; query?: string; selectedId?: string }) => void;
  slashTemplateItems?: SlashItem[];
  maxSlashSuggestions?: number;
}

const HTML_TAG_RE = /<\/?[a-z][\s\S]*>/i;

const isHtmlContent = (value: string) => HTML_TAG_RE.test(value);

const normalizeInitialContent = (value: string) => {
  if (!value.trim()) return '<p></p>';
  if (isHtmlContent(value)) return value;
  return toPersonalNotePreviewHtml(value);
};

// Define extensions at module level to prevent duplicate warnings across instances
const editorExtensions = [
  StarterKit.configure({
    heading: { levels: [1, 2] },
  }),
  Underline,
  TextStyle,
  Color,
  Table.configure({ resizable: true }),
  TableRow,
  TableHeader,
  TableCell,
  TaskList,
  TaskItem.configure({
    nested: true,
  }),
];

type ToolbarButtonProps = {
  active?: boolean;
  onClick: () => void;
  title: string;
  children: React.ReactNode;
};

const ToolbarButton: React.FC<ToolbarButtonProps> = ({ active = false, onClick, title, children }) => (
  <button
    type="button"
    onMouseDown={(e) => e.preventDefault()}
    onClick={onClick}
    className={`p-2 md:p-1.5 rounded transition-colors ${active ? 'bg-[#CC561E]/15 text-[#CC561E]' : 'text-slate-600 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-800'}`}
    title={title}
  >
    {children}
  </button>
);

export const PersonalNoteEditor: React.FC<PersonalNoteEditorProps> = ({
  value,
  onChange,
  autoFocus = false,
  placeholder = "Start writing... Use /task to insert a template.",
  minHeight = 220,
  onSlashCommand,
  slashTemplateItems = [],
  maxSlashSuggestions = 8,
}) => {
  const normalizeForSearch = (input: string): string =>
    String(input || '')
      .toLocaleLowerCase('tr-TR')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .trim();
  const resolveSlashCommand = (token: string): SlashCommandType | null => {
    const raw = token.toLocaleLowerCase('tr-TR');
    if (raw === '/task' || raw === '/template') return 'template';
    return null;
  };
  const [selectedColor, setSelectedColor] = useState('#0f172a');
  const [slashMenu, setSlashMenu] = useState<{
    command: SlashCommandType;
    query: string;
    items: SlashItem[];
    blockStart: number;
    selectedIndex: number;
  } | null>(null);
  const syncingFromValue = useRef(false);
  const slashMenuRef = useRef<typeof slashMenu>(null);
  const onSlashCommandRef = useRef(onSlashCommand);
  const slashTemplateItemsRef = useRef(slashTemplateItems);
  const maxSlashSuggestionsRef = useRef(maxSlashSuggestions);
  const updateSlashMenuFromEditorRef = useRef<(currentEditor: any) => void>(() => { });
  const editorHeightStyle = { ['--note-editor-min-height' as string]: `${minHeight}px` } as React.CSSProperties;

  useEffect(() => {
    slashMenuRef.current = slashMenu;
  }, [slashMenu]);

  useEffect(() => {
    onSlashCommandRef.current = onSlashCommand;
  }, [onSlashCommand]);

  useEffect(() => {
    slashTemplateItemsRef.current = slashTemplateItems;
  }, [slashTemplateItems]);

  useEffect(() => {
    maxSlashSuggestionsRef.current = maxSlashSuggestions;
  }, [maxSlashSuggestions]);

  updateSlashMenuFromEditorRef.current = (currentEditor) => {
    if (!onSlashCommandRef.current) {
      if (slashMenuRef.current) setSlashMenu(null);
      return;
    }
    const { state } = currentEditor;
    const { from, to } = state.selection;
    if (from !== to) {
      if (slashMenuRef.current) setSlashMenu(null);
      return;
    }

    const $from = state.doc.resolve(from);
    const blockStart = $from.start();
    const textBeforeCursor = state.doc.textBetween(blockStart, from, '\n', '\0');
    const match = textBeforeCursor.match(/^\s*(\/[^\s]+)(?:\s+(.+))?\s*$/u);
    if (!match) {
      if (slashMenuRef.current) setSlashMenu(null);
      return;
    }

    const command = resolveSlashCommand(match[1]);
    if (!command) {
      if (slashMenuRef.current) setSlashMenu(null);
      return;
    }

    const query = (match[2] || '').trim();
    const sourceItems = slashTemplateItemsRef.current;
    const normalizedQuery = normalizeForSearch(query);
    const filtered = sourceItems.filter((item) => {
      if (!normalizedQuery) return true;
      return normalizeForSearch(item.label).includes(normalizedQuery);
    });
    const limited = filtered.slice(0, Math.max(1, maxSlashSuggestionsRef.current));

    setSlashMenu((prev) => ({
      command,
      query,
      items: limited,
      blockStart,
      selectedIndex: Math.min(prev?.selectedIndex || 0, Math.max(limited.length - 1, 0)),
    }));
  };

  const editor = useEditor({
    extensions: useMemo(() => [...editorExtensions, Placeholder.configure({ placeholder })], [placeholder]),
    content: normalizeInitialContent(value),
    autofocus: autoFocus ? 'end' : false,
    editorProps: {
      attributes: {
        class: 'personal-note-prosemirror',
      },
      handleKeyDown: (view, event) => {
        const activeMenu = slashMenuRef.current;
        if (activeMenu) {
          if (event.key === 'Escape') {
            setSlashMenu(null);
            event.preventDefault();
            return true;
          }
          if (event.key === 'ArrowDown') {
            if (activeMenu.items.length > 0) {
              setSlashMenu((prev) => {
                if (!prev || prev.items.length === 0) return prev;
                return { ...prev, selectedIndex: (prev.selectedIndex + 1) % prev.items.length };
              });
              event.preventDefault();
              return true;
            }
          }
          if (event.key === 'ArrowUp') {
            if (activeMenu.items.length > 0) {
              setSlashMenu((prev) => {
                if (!prev || prev.items.length === 0) return prev;
                return { ...prev, selectedIndex: (prev.selectedIndex - 1 + prev.items.length) % prev.items.length };
              });
              event.preventDefault();
              return true;
            }
          }
          if (['Enter', 'Tab'].includes(event.key) && activeMenu.items.length > 0 && onSlashCommandRef.current) {
            const selected = activeMenu.items[activeMenu.selectedIndex] || activeMenu.items[0];
            const { state } = view;
            const { from } = state.selection;
            const tr = state.tr.delete(activeMenu.blockStart, from);
            view.dispatch(tr);
            event.preventDefault();
            onSlashCommandRef.current({
              command: activeMenu.command,
              query: selected.label,
              selectedId: selected.id,
            });
            setSlashMenu(null);
            return true;
          }
        }

        if (!onSlashCommandRef.current) return false;
        if (![' ', 'Enter', 'Tab'].includes(event.key)) return false;

        const { state } = view;
        const { from } = state.selection;
        const $from = state.doc.resolve(from);
        const blockStart = $from.start();
        const textBeforeCursor = state.doc.textBetween(blockStart, from, '\n', '\0');
        const match = textBeforeCursor.match(/^\s*(\/[^\s]+)(?:\s+(.+))?\s*$/u);
        if (!match) return false;

        const rawCommand = match[1];
        const query = (match[2] || '').trim();
        const command = resolveSlashCommand(rawCommand);
        if (!command) return false;

        const tr = state.tr.delete(blockStart, from);
        view.dispatch(tr);
        event.preventDefault();
        onSlashCommandRef.current({ command, query: query || undefined });
        setSlashMenu(null);
        return true;
      },
    },
    onUpdate: ({ editor: currentEditor }) => {
      if (syncingFromValue.current) return;
      onChange(currentEditor.getHTML());
      updateSlashMenuFromEditorRef.current(currentEditor);
    },
  });

  useEffect(() => {
    if (!editor) return;
    const next = normalizeInitialContent(value);
    const current = editor.getHTML();
    if (current === next) return;
    syncingFromValue.current = true;
    editor.commands.setContent(next, { emitUpdate: false });
    syncingFromValue.current = false;
  }, [editor, value]);


  return (
    <div className="rounded-xl border border-[#E6EAF2] dark:border-slate-700 bg-white dark:bg-slate-950 overflow-hidden">
      <div className="flex flex-wrap items-center px-2 md:px-3 py-1.5 md:py-2 border-b border-[#E6EAF2] dark:border-slate-700 bg-[#F8FAFC] dark:bg-slate-900 gap-1 md:gap-1.5">
        {/* All Formatting Tools in one wrapping flow */}
        <ToolbarButton active={!!editor?.isActive('heading', { level: 1 })} onClick={() => editor?.chain().focus().toggleHeading({ level: 1 }).run()} title="Heading 1">
          <Heading1 size={18} className="md:w-3.5 md:h-3.5" />
        </ToolbarButton>
        <ToolbarButton active={!!editor?.isActive('heading', { level: 2 })} onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()} title="Heading 2">
          <Heading2 size={18} className="md:w-3.5 md:h-3.5" />
        </ToolbarButton>
        <ToolbarButton active={!!editor?.isActive('bold')} onClick={() => editor?.chain().focus().toggleBold().run()} title="Bold">
          <Bold size={18} className="md:w-3.5 md:h-3.5" />
        </ToolbarButton>
        <ToolbarButton active={!!editor?.isActive('italic')} onClick={() => editor?.chain().focus().toggleItalic().run()} title="Italic">
          <Italic size={18} className="md:w-3.5 md:h-3.5" />
        </ToolbarButton>
        <ToolbarButton active={!!editor?.isActive('underline')} onClick={() => editor?.chain().focus().toggleUnderline().run()} title="Underline">
          <UnderlineIcon size={18} className="md:w-3.5 md:h-3.5" />
        </ToolbarButton>

        {/* Separator / Spacer for visual grouping on desktop */}
        <div className="hidden md:block w-px h-4 bg-slate-300 dark:bg-slate-700 mx-1" />

        <div className="inline-flex items-center gap-1 px-1.5 py-1 rounded border border-[#E6EAF2] dark:border-slate-700 bg-white dark:bg-slate-900">
          <Palette size={16} className="text-slate-500 md:w-3 md:h-3" />
          <input
            type="color"
            value={selectedColor}
            onChange={(e) => {
              const nextColor = e.target.value;
              setSelectedColor(nextColor);
              editor?.chain().focus().setColor(nextColor).run();
            }}
            className="w-7 h-7 md:w-5 md:h-5 p-0 border-0 bg-transparent cursor-pointer"
            title="Text Color"
          />
          <ToolbarButton active={false} onClick={() => editor?.chain().focus().unsetColor().run()} title="Clear Text Color">
            <Eraser size={16} className="md:w-3 md:h-3" />
          </ToolbarButton>
        </div>

        <ToolbarButton active={!!editor?.isActive('bulletList')} onClick={() => editor?.chain().focus().toggleBulletList().run()} title="Bullet List">
          <List size={18} className="md:w-3.5 md:h-3.5" />
        </ToolbarButton>
        <ToolbarButton active={!!editor?.isActive('orderedList')} onClick={() => editor?.chain().focus().toggleOrderedList().run()} title="Numbered List">
          <ListOrdered size={18} className="md:w-3.5 md:h-3.5" />
        </ToolbarButton>
        <ToolbarButton active={!!editor?.isActive('taskList')} onClick={() => editor?.chain().focus().toggleTaskList().run()} title="Checklist">
          <CheckSquare size={18} className="md:w-3.5 md:h-3.5" />
        </ToolbarButton>
        <ToolbarButton active={!!editor?.isActive('blockquote')} onClick={() => editor?.chain().focus().toggleBlockquote().run()} title="Quote">
          <Quote size={18} className="md:w-3.5 md:h-3.5" />
        </ToolbarButton>

        <div className="hidden md:block w-px h-4 bg-slate-300 dark:bg-slate-700 mx-1" />

        <ToolbarButton active={!!editor?.isActive('table')} onClick={() => editor?.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()} title="Insert Table">
          <Table2 size={18} className="md:w-3.5 md:h-3.5" />
        </ToolbarButton>
        <ToolbarButton active={false} onClick={() => editor?.chain().focus().addRowAfter().run()} title="Add Row">
          <Rows3 size={18} className="md:w-3.5 md:h-3.5" />
        </ToolbarButton>
        <ToolbarButton active={false} onClick={() => editor?.chain().focus().addColumnAfter().run()} title="Add Column">
          <Columns3 size={18} className="md:w-3.5 md:h-3.5" />
        </ToolbarButton>
        <ToolbarButton active={false} onClick={() => editor?.chain().focus().deleteTable().run()} title="Delete Table">
          <Trash2 size={18} className="md:w-3.5 md:h-3.5" />
        </ToolbarButton>
      </div>

      <div className="relative bg-white dark:bg-slate-950 text-slate-900 dark:text-white" style={editorHeightStyle}>
        <EditorContent editor={editor} />
        {slashMenu && (
          <div className="absolute left-3 top-3 z-20 w-[min(420px,calc(100%-1.5rem))] rounded-lg border border-[#E6EAF2] dark:border-slate-700 bg-white dark:bg-slate-900 shadow-xl">
            <div className="px-3 py-2 border-b border-[#E6EAF2] dark:border-slate-700 text-[11px] font-semibold text-slate-500 dark:text-slate-400">
              Şablon Seç {slashMenu.query ? `— "${slashMenu.query}"` : ''}
            </div>
            {slashMenu.items.length === 0 ? (
              <div className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">
                Eslesen sonuc yok.
              </div>
            ) : (
              <div className="max-h-56 overflow-auto py-1">
                {slashMenu.items.map((item, index) => (
                  <button
                    key={`${slashMenu.command}-${item.id}`}
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => {
                      if (!editor || !onSlashCommandRef.current) return;
                      const from = editor.state.selection.from;
                      editor.view.dispatch(editor.state.tr.delete(slashMenu.blockStart, from));
                      onSlashCommandRef.current({
                        command: slashMenu.command,
                        query: item.label,
                        selectedId: item.id,
                      });
                      setSlashMenu(null);
                      editor.commands.focus();
                    }}
                    className={`w-full text-left px-3 py-2 text-sm ${index === slashMenu.selectedIndex
                      ? 'bg-[#CC561E]/10 text-[#CC561E]'
                      : 'text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800'
                      }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            )}
            <div className="px-3 py-1.5 border-t border-[#E6EAF2] dark:border-slate-700 text-[10px] text-slate-500 dark:text-slate-400">
              Enter/Tab sec | Esc kapat
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
