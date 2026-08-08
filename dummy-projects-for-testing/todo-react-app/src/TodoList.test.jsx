import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import TodoList from './TodoList';

test('shows all todos by default', () => {
  render(<TodoList />);
  expect(screen.getByText('Buy milk')).toBeInTheDocument();
  expect(screen.getByText('Walk the dog')).toBeInTheDocument();
  expect(screen.getByText('Write report')).toBeInTheDocument();
});

test('Active filter shows only incomplete todos', () => {
  render(<TodoList />);
  fireEvent.click(screen.getByText('Active'));
  expect(screen.getByText('Buy milk')).toBeInTheDocument();
  expect(screen.getByText('Write report')).toBeInTheDocument();
  expect(screen.queryByText('Walk the dog')).not.toBeInTheDocument();
});

test('Completed filter shows only completed todos', () => {
  render(<TodoList />);
  fireEvent.click(screen.getByText('Completed'));
  expect(screen.getByText('Walk the dog')).toBeInTheDocument();
  expect(screen.queryByText('Buy milk')).not.toBeInTheDocument();
  expect(screen.queryByText('Write report')).not.toBeInTheDocument();
});
