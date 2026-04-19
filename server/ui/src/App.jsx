import React, { useState, useEffect, Suspense } from 'react';

import useIsMobile from './hooks/useIsMobile.js';

const DesktopApp = React.lazy(() => import('./DesktopApp.jsx'));
const MobileApp = React.lazy(() => import('./MobileApp.jsx'));

function App() {
    const isMobile = useIsMobile();
    const [dark, setDark] = useState(false);

    useEffect(() => {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        setDark(prefersDark);
    }, []);

    useEffect(() => {
        document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    }, [dark]);

    const toggleTheme = () => setDark((d) => !d);

    return (
        <Suspense fallback={null}>
            {isMobile
                ? <MobileApp dark={dark} onToggleTheme={toggleTheme} />
                : <DesktopApp dark={dark} onToggleTheme={toggleTheme} />
            }
        </Suspense>
    );
}

export default App;
