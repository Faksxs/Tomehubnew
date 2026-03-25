import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

const SimpleComponent = ({ title }: { title: string }) => (
  <div>
    <h1>{title}</h1>
    <p>Test Content</p>
  </div>
);

describe('SimpleComponent', () => {
  it('renders the title correctly', () => {
    render(<SimpleComponent title="Hello TomeHub" />);
    expect(screen.getByText('Hello TomeHub')).toBeInTheDocument();
  });

  it('contains the test paragraph', () => {
    render(<SimpleComponent title="Title" />);
    expect(screen.getByText('Test Content')).toBeInTheDocument();
  });
});
