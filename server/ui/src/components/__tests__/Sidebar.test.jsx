import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Sidebar from '../Sidebar.jsx';

const COLLAPSE_KEY = 'computron_sidebar_collapsed';

function setup(props = {}) {
    const onPanelToggle = vi.fn();
    const onToggleTheme = vi.fn();
    const onNewConversation = vi.fn();
    render(
        <Sidebar
            activePanel={null}
            onPanelToggle={onPanelToggle}
            dark={true}
            onToggleTheme={onToggleTheme}
            onNewConversation={onNewConversation}
            {...props}
        />,
    );
    return { onPanelToggle, onToggleTheme, onNewConversation };
}

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

describe('Sidebar', () => {
    it('starts expanded with the wordmark and nav labels visible', () => {
        setup();
        expect(screen.getByTestId('sidebar')).toHaveAttribute('data-collapsed', 'false');
        expect(screen.getByText('COMPUTRON')).toBeInTheDocument();
        expect(screen.getByText('New chat')).toBeInTheDocument();
        expect(screen.getByText('Goals')).toBeInTheDocument();
    });

    it('collapses on toggle and hides labels', async () => {
        const user = userEvent.setup();
        setup();
        await user.click(screen.getByTestId('sidebar-toggle'));
        expect(screen.getByTestId('sidebar')).toHaveAttribute('data-collapsed', 'true');
        expect(screen.queryByText('COMPUTRON')).not.toBeInTheDocument();
        expect(screen.queryByText('New chat')).not.toBeInTheDocument();
        expect(screen.queryByText('Goals')).not.toBeInTheDocument();
    });

    it('persists the collapsed state to localStorage', async () => {
        const user = userEvent.setup();
        setup();
        await user.click(screen.getByTestId('sidebar-toggle'));
        expect(localStorage.getItem(COLLAPSE_KEY)).toBe('1');
        await user.click(screen.getByTestId('sidebar-toggle'));
        expect(localStorage.getItem(COLLAPSE_KEY)).toBe('0');
    });

    it('reads the initial collapsed state from localStorage', () => {
        localStorage.setItem(COLLAPSE_KEY, '1');
        setup();
        expect(screen.getByTestId('sidebar')).toHaveAttribute('data-collapsed', 'true');
    });

    it('fires onNewConversation from the New chat button', async () => {
        const user = userEvent.setup();
        const { onNewConversation } = setup();
        await user.click(screen.getByTestId('sidebar-new-chat'));
        expect(onNewConversation).toHaveBeenCalledOnce();
    });

    it('fires onToggleTheme from the theme button', async () => {
        const user = userEvent.setup();
        const { onToggleTheme } = setup();
        await user.click(screen.getByTestId('sidebar-theme-toggle'));
        expect(onToggleTheme).toHaveBeenCalledOnce();
    });

    it('opens a panel from a nav item', async () => {
        const user = userEvent.setup();
        const { onPanelToggle } = setup();
        await user.click(screen.getByTestId('sidebar-nav-goals'));
        expect(onPanelToggle).toHaveBeenCalledWith('goals');
    });

    it('toggles an already-active panel closed', async () => {
        const user = userEvent.setup();
        const { onPanelToggle } = setup({ activePanel: 'goals' });
        await user.click(screen.getByTestId('sidebar-nav-goals'));
        expect(onPanelToggle).toHaveBeenCalledWith(null);
    });

    it('opens settings from the footer', async () => {
        const user = userEvent.setup();
        const { onPanelToggle } = setup();
        await user.click(screen.getByTestId('sidebar-settings'));
        expect(onPanelToggle).toHaveBeenCalledWith('settings');
    });

it('hides the desktop button unless desktop is enabled', () => {
        setup();
        expect(screen.queryByTestId('sidebar-desktop')).not.toBeInTheDocument();
    });

    it('shows the desktop button and fires onOpenDesktop when enabled', async () => {
        const user = userEvent.setup();
        const onOpenDesktop = vi.fn();
        setup({ desktopEnabled: true, onOpenDesktop });
        await user.click(screen.getByTestId('sidebar-desktop'));
        expect(onOpenDesktop).toHaveBeenCalledOnce();
    });
});
