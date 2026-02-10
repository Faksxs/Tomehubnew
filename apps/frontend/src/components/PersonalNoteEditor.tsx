import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Bold, Heading1, Heading2, Italic, List, ListOrdered, CheckSquare, Underline, Quote, Eye, PencilLine, Table2, Rows3, Columns3, Trash2, Palette, Eraser } from 'lucide-react';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import UnderlineExtension from '@tiptap/extension-underline';
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

interface PersonalNoteEditorProps {
  value: string;
  onChange: (next: string) => void;
  autoFocus?: boolean;
  placeholder?: string;
  minHeight?: number;
}

const HTML_TAG_RE = /<\/?[a-z][\s\S]*>/i;

const isHtmlContent = (value: string) => HTML_TAG_RE.test(value);

const normalizeInitialContent = (value: string) => {
  if (!value.trim()) return '<p></p>';
  if (isHtmlContent(value)) return value;
  return toPersonalNotePreviewHtml(value);
};

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
    className={`p-1.5 rounded transition-colors ${active ? 'bg-[#CC561E]/15 text-[#CC561E]' : 'text-slate-600 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-800'}`}
    title={title}
  >
    {children}
  </button>
);

export const PersonalNoteEditor: React.FC<PersonalNoteEditorProps> = ({
  value,
  onChange,
  autoFocus = false,
  placeholder = "Start writing... Use toolbar for lists, checklist, headings, and emphasis.",
  minHeight = 220,
}) => {
  const [mode, setMode] = useState<'write' | 'preview'>('write');
  const [selectedColor, setSelectedColor] = useState('#0f172a');
  const syncingFromValue = useRef(false);
  const editorHeightStyle = { ['--note-editor-min-height' as string]: `${minHeight}px` } as React.CSSProperties;

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2] },
      }),
      UnderlineExtension,
      TextStyle,
      Color,
      Table.configure({ resizable: true }),
      TableRow,
      TableHeader,
      TableCell,
      TaskList,
      TaskItem.configure({ nested: true }),
      Placeholder.configure({ placeholder }),
    ],
    content: normalizeInitialContent(value),
    autofocus: autoFocus ? 'end' : false,
    editorProps: {
      attributes: {
        class: 'personal-note-prosemirror',
      },
    },
    onUpdate: ({ editor: currentEditor }) => {
      if (syncingFromValue.current) return;
      onChange(currentEditor.getHTML());
    },
  });

  useEffect(() => {
    if (!editor) return;
    const next = normalizeInitialContent(value);
    const current = editor.getHTML();
    if (current === next) return;
    syncingFromValue.current = true;
    editor.commands.setContent(next, false);
    syncingFromValue.current = false;
  }, [editor, value]);

  const previewHtml = useMemo(() => toPersonalNotePreviewHtml(value), [value]);

  return (
    <div className="rounded-xl border border-[#E6EAF2] dark:border-slate-700 bg-white dark:bg-slate-950 overflow-hidden">
      <div className="flex items-center justify-between px-2 md:px-3 py-2 border-b border-[#E6EAF2] dark:border-slate-700 bg-[#F8FAFC] dark:bg-slate-900">
        <div className="flex items-center gap-1 flex-wrap">
          <ToolbarButton active={!!editor?.isActive('heading', { level: 1 })} onClick={() => editor?.chain().focus().toggleHeading({ level: 1 }).run()} title="Heading 1">
            <Heading1 size={14} />
          </ToolbarButton>
          <ToolbarButton active={!!editor?.isActive('heading', { level: 2 })} onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()} title="Heading 2">
            <Heading2 size={14} />
          </ToolbarButton>
          <ToolbarButton active={!!editor?.isActive('bold')} onClick={() => editor?.chain().focus().toggleBold().run()} title="Bold">
            <Bold size={14} />
          </ToolbarButton>
          <ToolbarButton active={!!editor?.isActive('italic')} onClick={() => editor?.chain().focus().toggleItalic().run()} title="Italic">
            <Italic size={14} />
          </ToolbarButton>
          <ToolbarButton active={!!editor?.isActive('underline')} onClick={() => editor?.chain().focus().toggleUnderline().run()} title="Underline">
            <Underline size={14} />
          </ToolbarButton>
          <div className="inline-flex items-center gap-1 px-1 py-0.5 rounded border border-[#E6EAF2] dark:border-slate-700 bg-white dark:bg-slate-900">
            <Palette size={13} className="text-slate-500" />
            <input
              type="color"
              value={selectedColor}
              onChange={(e) => {
                const nextColor = e.target.value;
                setSelectedColor(nextColor);
                editor?.chain().focus().setColor(nextColor).run();
              }}
              className="w-5 h-5 p-0 border-0 bg-transparent cursor-pointer"
              title="Text Color"
            />
            <ToolbarButton active={false} onClick={() => editor?.chain().focus().unsetColor().run()} title="Clear Text Color">
              <Eraser size={12} />
            </ToolbarButton>
          </div>
          <ToolbarButton active={!!editor?.isActive('bulletList')} onClick={() => editor?.chain().focus().toggleBulletList().run()} title="Bullet List">
            <List size={14} />
          </ToolbarButton>
          <ToolbarButton active={!!editor?.isActive('orderedList')} onClick={() => editor?.chain().focus().toggleOrderedList().run()} title="Numbered List">
            <ListOrdered size={14} />
          </ToolbarButton>
          <ToolbarButton active={!!editor?.isActive('taskList')} onClick={() => editor?.chain().focus().toggleTaskList().run()} title="Checklist">
            <CheckSquare size={14} />
          </ToolbarButton>
          <ToolbarButton active={!!editor?.isActive('blockquote')} onClick={() => editor?.chain().focus().toggleBlockquote().run()} title="Quote">
            <Quote size={14} />
          </ToolbarButton>
          <ToolbarButton active={!!editor?.isActive('table')} onClick={() => editor?.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()} title="Insert Table">
            <Table2 size={14} />
          </ToolbarButton>
          <ToolbarButton active={false} onClick={() => editor?.chain().focus().addRowAfter().run()} title="Add Row">
            <Rows3 size={14} />
          </ToolbarButton>
          <ToolbarButton active={false} onClick={() => editor?.chain().focus().addColumnAfter().run()} title="Add Column">
            <Columns3 size={14} />
          </ToolbarButton>
          <ToolbarButton active={false} onClick={() => editor?.chain().focus().deleteTable().run()} title="Delete Table">
            <Trash2 size={14} />
          </ToolbarButton>
        </div>

        <div className="flex items-center bg-white dark:bg-slate-800 rounded-lg border border-[#E6EAF2] dark:border-slate-700">
          <button
            type="button"
            onClick={() => setMode('write')}
            className={`px-2.5 py-1 text-xs rounded-l-lg ${mode === 'write' ? 'bg-[#CC561E] text-white' : 'text-slate-500'}`}
          >
            <span className="inline-flex items-center gap-1"><PencilLine size={12} /> Write</span>
          </button>
          <button
            type="button"
            onClick={() => setMode('preview')}
            className={`px-2.5 py-1 text-xs rounded-r-lg ${mode === 'preview' ? 'bg-[#CC561E] text-white' : 'text-slate-500'}`}
          >
            <span className="inline-flex items-center gap-1"><Eye size={12} /> Preview</span>
          </button>
        </div>
      </div>

      {mode === 'write' ? (
        <div className="bg-white dark:bg-slate-950 text-slate-900 dark:text-white" style={editorHeightStyle}>
          <EditorContent editor={editor} />
        </div>
      ) : (
        <div
          className="personal-note-render p-3 md:p-4 max-w-none text-slate-800 dark:text-slate-200"
          style={{ minHeight }}
          dangerouslySetInnerHTML={{ __html: previewHtml }}
        />
      )}
    </div>
  );
};
