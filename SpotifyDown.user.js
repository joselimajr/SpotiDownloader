// ==UserScript==
// @name         SpotifyDown Token Grabber 
// @description  Get SpotifyDown token from network requests.
// @icon         https://www.google.com/s2/favicons?sz=64&domain=spotify.com
// @version      1.0
// @author       afkarxyz
// @namespace    https://github.com/afkarxyz/misc-scripts/
// @supportURL   https://github.com/afkarxyz/misc-scripts/issues
// @license      MIT
// @match        https://spotifydown.com/*
// @grant        none
// ==/UserScript==

(function() {
    'use strict';

    const COLORS = {
        default: '#156e30',
        hover: '#115c28',
        error: '#dc3545'
    };

    const SAMPLE_URL = 'https://open.spotify.com/track/2plbrEY59IikOBgBGLjaoe';
    const COPY_TIMEOUT = 2000;

    const addFontLink = () => {
        const link = document.createElement('link');
        link.href = 'https://fonts.googleapis.com/css2?family=Open+Sans:wght@400&display=swap';
        link.rel = 'stylesheet';
        document.head.appendChild(link);
    };

    const createButtonContainer = () => {
        const container = document.createElement('div');
        container.style.cssText = 'position:fixed;top:10px;right:10px;z-index:9999;display:flex;gap:10px;font-family:"Open Sans",sans-serif;';
        return container;
    };

    const createButton = (text) => {
        const btn = document.createElement('button');
        btn.innerHTML = text;
        btn.style.cssText = `
            padding:8px 16px;
            background:${COLORS.default};
            color:white;
            border:none;
            border-radius:4px;
            cursor:pointer;
            font-weight:400;
            font-family:"Open Sans",sans-serif;
            min-width:120px;
            transition:background-color 0.3s
        `;

        const handleHover = (isHover) => {
            if (btn.innerHTML !== 'No Token Found!') {
                btn.style.backgroundColor = isHover ? COLORS.hover : COLORS.default;
            }
        };

        btn.addEventListener('mouseover', () => handleHover(true));
        btn.addEventListener('mouseout', () => handleHover(false));
        return btn;
    };

    const resetButton = (btn, originalText) => {
        setTimeout(() => {
            btn.innerHTML = originalText;
            btn.style.backgroundColor = COLORS.default;
        }, COPY_TIMEOUT);
    };

    const copyToClipboard = async (text, btn, successText) => {
        await navigator.clipboard.writeText(text);
        btn.innerHTML = 'Copied!';
        resetButton(btn, successText);
    };

    const getSpotifyToken = () => {
        const requests = performance.getEntriesByType('resource')
            .filter(req => req.name.includes('spotifydown.com/download/'))
            .map(req => req.name.match(/\?token=(.+)$/)?.[1])
            .filter(Boolean);
        return requests[requests.length - 1] || null;
    };

    const handleTokenButton = async (btn) => {
        const token = getSpotifyToken();
        if (token) {
            await copyToClipboard(token, btn, 'Get Token');
        } else {
            btn.innerHTML = 'No Token Found!';
            btn.style.backgroundColor = COLORS.error;
            resetButton(btn, 'Get Token');
        }
    };

    const init = () => {
        addFontLink();
        const container = createButtonContainer();
        const sampleBtn = createButton('Sample URL');
        const tokenBtn = createButton('Get Token');

        sampleBtn.addEventListener('click', () => copyToClipboard(SAMPLE_URL, sampleBtn, 'Sample URL'));
        tokenBtn.addEventListener('click', () => handleTokenButton(tokenBtn));

        container.append(sampleBtn, tokenBtn);
        document.body.appendChild(container);
    };

    init();
})();
