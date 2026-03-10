import React, { useState } from 'react';
import { 
    Plus, 
    MoreHorizontal, 
    Calendar, 
    Tag, 
    CheckCircle2, 
    Circle, 
    Clock,
    ArrowRight,
    Search,
    Filter,
    X,
    Layout
} from 'lucide-react';

type TaskStatus = 'TODO' | 'IN_PROGRESS' | 'DONE';

interface Task {
    id: string;
    title: string;
    description?: string;
    status: TaskStatus;
    category?: string;
    dueDate?: string;
    priority?: 'low' | 'medium' | 'high';
}

const INITIAL_TASKS: Task[] = [
    {
        id: '1',
        title: 'Setup Notion Todo UI',
        description: 'Design the Kanban board with premium aesthetics',
        status: 'TODO',
        category: 'productivity',
        dueDate: 'June 19, 2025',
        priority: 'high'
    },
    {
        id: '2',
        title: 'Integrate Firestore persistence',
        description: 'Connect the todo board to the backend',
        status: 'IN_PROGRESS',
        category: 'dev',
        dueDate: 'June 20, 2025',
        priority: 'medium'
    },
    {
        id: '3',
        title: 'Initial Concept Review',
        description: 'Gather feedback on the new task management feature',
        status: 'DONE',
        category: 'feedback',
        dueDate: 'June 18, 2025',
        priority: 'low'
    }
];

export const TodoBoard: React.FC<{ onBack: () => void }> = ({ onBack }) => {
    const [tasks, setTasks] = useState<Task[]>(INITIAL_TASKS);
    const [searchQuery, setSearchQuery] = useState('');
    const [isAddingIn, setIsAddingIn] = useState<TaskStatus | null>(null);
    const [newTaskTitle, setNewTaskTitle] = useState('');

    const filteredTasks = tasks.filter(t => 
        t.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.category?.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const moveTask = (id: string, newStatus: TaskStatus) => {
        setTasks(prev => prev.map(t => t.id === id ? { ...t, status: newStatus } : t));
    };

    const addTask = (status: TaskStatus) => {
        if (!newTaskTitle.trim()) return;
        
        const newTask: Task = {
            id: Math.random().toString(36).substr(2, 9),
            title: newTaskTitle,
            status,
            category: 'general',
            dueDate: new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
        };

        setTasks(prev => [...prev, newTask]);
        setNewTaskTitle('');
        setIsAddingIn(null);
    };

    const StatusColumn = ({ status, label, color, icon: Icon }: { 
        status: TaskStatus, 
        label: string, 
        color: string,
        icon: any
    }) => {
        const columnTasks = filteredTasks.filter(t => t.status === status);
        
        return (
            <div className="flex flex-col w-full min-w-[300px] max-w-[400px]">
                <div className="flex items-center justify-between mb-4 px-2">
                    <div className="flex items-center gap-2">
                        <span className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider ${color}`}>
                            {label}
                        </span>
                        <span className="text-slate-400 dark:text-slate-500 text-sm font-medium">
                            {columnTasks.length}
                        </span>
                    </div>
                    <button 
                        onClick={() => setIsAddingIn(status)}
                        className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-md text-slate-400 transition-colors"
                    >
                        <Plus size={18} />
                    </button>
                </div>

                <div className="flex flex-col gap-3 min-h-[500px]">
                    {columnTasks.map(task => (
                        <div 
                            key={task.id}
                            className="bg-white dark:bg-slate-900 border border-[#E6EAF2] dark:border-slate-800 rounded-xl p-4 shadow-sm hover:shadow-md transition-all group relative animate-in fade-in slide-in-from-bottom-2 duration-300"
                        >
                            <div className="flex justify-between items-start mb-2">
                                <h3 className="text-sm font-semibold text-slate-900 dark:text-white leading-snug">
                                    {task.title}
                                </h3>
                                <button className="opacity-0 group-hover:opacity-100 p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded transition-all">
                                    <MoreHorizontal size={14} className="text-slate-400" />
                                </button>
                            </div>

                            {task.description && (
                                <p className="text-xs text-slate-500 dark:text-slate-400 mb-3 line-clamp-2">
                                    {task.description}
                                </p>
                            )}

                            <div className="flex flex-wrap gap-2 items-center mt-3">
                                {task.dueDate && (
                                    <div className="flex items-center gap-1 text-[10px] text-slate-400 font-medium">
                                        <Calendar size={10} />
                                        {task.dueDate}
                                    </div>
                                )}
                                {task.category && (
                                    <span className="px-2 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 rounded-full text-[9px] font-bold uppercase tracking-tight">
                                        {task.category}
                                    </span>
                                )}
                            </div>

                            <div className="absolute bottom-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-all">
                                {status !== 'TODO' && (
                                    <button 
                                        onClick={() => moveTask(task.id, 'TODO')}
                                        className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded text-slate-400"
                                        title="Move to Todo"
                                    >
                                        <ArrowRight size={12} className="rotate-180" />
                                    </button>
                                )}
                                {status !== 'IN_PROGRESS' && (
                                    <button 
                                        onClick={() => moveTask(task.id, 'IN_PROGRESS')}
                                        className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded text-slate-400"
                                        title="Move to In Progress"
                                    >
                                        <Clock size={12} />
                                    </button>
                                )}
                                {status !== 'DONE' && (
                                    <button 
                                        onClick={() => moveTask(task.id, 'DONE')}
                                        className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded text-slate-400"
                                        title="Move to Done"
                                    >
                                        <CheckCircle2 size={12} />
                                    </button>
                                )}
                            </div>
                        </div>
                    ))}

                    <div className="mt-1">
                        {isAddingIn === status ? (
                            <div className="bg-white dark:bg-slate-900 border border-[#CC561E]/30 rounded-xl p-3 shadow-lg animate-in zoom-in-95 duration-200">
                                <input 
                                    autoFocus
                                    placeholder="Enter task title..."
                                    className="w-full bg-transparent text-sm text-slate-900 dark:text-white outline-none mb-3"
                                    value={newTaskTitle}
                                    onChange={(e) => setNewTaskTitle(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && addTask(status)}
                                />
                                <div className="flex justify-end gap-2">
                                    <button 
                                        onClick={() => setIsAddingIn(null)}
                                        className="px-3 py-1 text-xs font-medium text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                                    >
                                        Cancel
                                    </button>
                                    <button 
                                        onClick={() => addTask(status)}
                                        className="px-3 py-1 bg-[#262D40] text-white rounded-lg text-xs font-medium hover:bg-[#1d2333]"
                                    >
                                        Add Task
                                    </button>
                                </div>
                            </div>
                        ) : (
                            <button 
                                onClick={() => setIsAddingIn(status)}
                                className="w-full flex items-center gap-2 px-3 py-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800/50 rounded-lg transition-all text-sm font-medium group"
                            >
                                <Plus size={16} className="group-hover:scale-110 transition-transform" />
                                New Task
                            </button>
                        )}
                    </div>
                </div>
            </div>
        );
    };

    return (
        <div className="max-w-7xl w-full mx-auto p-4 md:p-8 lg:p-10 animate-in fade-in duration-500">
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between mb-8 gap-4">
                <div className="flex items-center gap-4">
                    <div className="p-3 bg-[#262D40] rounded-2xl border border-[#262D40]/80 shadow-md shadow-[#262D40]/10">
                        <CheckCircle2 size={24} className="text-white" />
                    </div>
                    <div>
                        <h1 className="text-2xl md:text-3xl font-bold text-slate-900 dark:text-white tracking-tight">
                            Todo Board
                        </h1>
                        <p className="text-slate-500 dark:text-slate-400 text-xs md:text-sm font-medium mt-1">
                            {tasks.filter(t => t.status === 'DONE').length}/{tasks.length} tasks completed
                        </p>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 w-4 h-4" />
                        <input 
                            type="text"
                            placeholder="Filter tasks..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="pl-10 pr-4 py-2 bg-white dark:bg-slate-900 border border-[#E6EAF2] dark:border-slate-800 rounded-xl text-sm outline-none focus:ring-2 focus:ring-[#CC561E]/50 transition-all w-full md:w-64"
                        />
                    </div>
                    <button className="p-2.5 bg-white dark:bg-slate-900 border border-[#E6EAF2] dark:border-slate-800 rounded-xl text-slate-500 hover:text-slate-700 transition-colors shadow-sm">
                        <Filter size={18} />
                    </button>
                </div>
            </div>

            {/* Kanban Columns */}
            <div className="flex flex-col lg:flex-row gap-8 overflow-x-auto pb-8 scrollbar-hide">
                <StatusColumn 
                    status="TODO" 
                    label="Todo" 
                    color="bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400" 
                    icon={Circle}
                />
                <StatusColumn 
                    status="IN_PROGRESS" 
                    label="In Progress" 
                    color="bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400" 
                    icon={Clock}
                />
                <StatusColumn 
                    status="DONE" 
                    label="Done" 
                    color="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400" 
                    icon={CheckCircle2}
                />

                {/* Add Group Placeholder */}
                <div className="flex flex-col w-[200px] shrink-0 opacity-40 hover:opacity-100 transition-opacity cursor-not-allowed group">
                    <div className="flex items-center gap-2 mb-4 px-2">
                        <Plus size={14} className="text-slate-400 group-hover:text-[#CC561E]" />
                        <span className="text-sm font-medium text-slate-400">Add Group</span>
                    </div>
                </div>
            </div>
            
            {/* Quick Tips / Dashboard links */}
            <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="p-4 rounded-2xl bg-gradient-to-br from-white to-slate-50 dark:from-slate-900 dark:to-slate-800/50 border border-[#E6EAF2] dark:border-slate-800 shadow-sm">
                    <Layout className="text-[#CC561E] mb-3" size={20} />
                    <h4 className="text-sm font-bold text-slate-900 dark:text-white mb-1">Board View</h4>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400">Visual Kanban for tracking progress across different stages.</p>
                </div>
                <div className="p-4 rounded-2xl bg-gradient-to-br from-white to-slate-50 dark:from-slate-900 dark:to-slate-800/50 border border-[#E6EAF2] dark:border-slate-800 shadow-sm opacity-50">
                    <Layout className="text-slate-400 mb-3" size={20} />
                    <h4 className="text-sm font-bold text-slate-900 dark:text-white mb-1">Table View</h4>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400">Structured data view for batch editing and sorting. (Coming soon)</p>
                </div>
                <div className="p-4 rounded-2xl bg-gradient-to-br from-[#262D40] to-[#1d2333] border border-white/5 shadow-lg shadow-[#262D40]/20">
                    <Plus className="text-[#FFB58D] mb-3" size={20} />
                    <h4 className="text-sm font-bold text-white mb-1">Personal Knowledge OS</h4>
                    <p className="text-[11px] text-slate-300">Connect your tasks with your notes and library highlights.</p>
                </div>
            </div>
        </div>
    );
};
