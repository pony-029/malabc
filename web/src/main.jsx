import React from 'react';
import { createRoot } from 'react-dom/client';
import { Theme } from '@astryxdesign/core/theme';
import '@astryxdesign/core/astryx.css';
import { themes, defaultThemeSlug } from '../astryx-themes.js';
import App from './App.jsx';

createRoot(document.getElementById('root')).render(
  <Theme theme={themes[defaultThemeSlug]}>
    <App />
  </Theme>,
);
