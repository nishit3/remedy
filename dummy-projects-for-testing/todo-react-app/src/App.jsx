import React from 'react';
import TodoList from './TodoList';

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>My Todos</h1>
      </header>
      <main>
        <TodoList />
      </main>
    </div>
  );
}
