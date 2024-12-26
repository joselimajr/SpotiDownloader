// ==UserScript==
// @name         Token Grabber 
// @description  Get SpotifyDown token from network requests.
// @icon         https://raw.githubusercontent.com/afkarxyz/SpotifyDown-GUI/refs/heads/main/SpotifyDown.svg
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

    const ICONS = {
        key: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" style="width: 16px; height: 16px; fill: white; margin-right: 8px;"><path d="M336 352c97.2 0 176-78.8 176-176S433.2 0 336 0S160 78.8 160 176c0 18.7 2.9 36.8 8.3 53.7L7 391c-4.5 4.5-7 10.6-7 17l0 80c0 13.3 10.7 24 24 24l80 0c13.3 0 24-10.7 24-24l0-40 40 0c13.3 0 24-10.7 24-24l0-40 40 0c6.4 0 12.5-2.5 17-7l33.3-33.3c16.9 5.4 35 8.3 53.7 8.3zM376 96a40 40 0 1 1 0 80 40 40 0 1 1 0-80z"/></svg>`,
        error: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" style="width: 16px; height: 16px; fill: white; margin-right: 8px;"><path d="M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zm0-384c13.3 0 24 10.7 24 24l0 112c0 13.3-10.7 24-24 24s-24-10.7-24-24l0-112c0-13.3 10.7-24 24-24zM224 352a32 32 0 1 1 64 0 32 32 0 1 1 -64 0z"/></svg>`
    };
    
    const COPY_TIMEOUT = 500;

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

    const createButton = (text, icon) => {
        const btn = document.createElement('button');
        btn.innerHTML = `${icon}<span>${text}</span>`;
        btn.style.cssText = `
            padding:8px 16px;
            background:${COLORS.default};
            color:white;
            border:none;
            border-radius:25px;
            cursor:pointer;
            font-weight:400;
            font-family:"Open Sans",sans-serif;
            min-width:140px;
            transition:background-color 0.1s;
            display:flex;
            align-items:center;
            justify-content:center;
        `;

        const handleHover = (isHover) => {
            if (!btn.querySelector('span').textContent.includes('Not Found')) {
                btn.style.backgroundColor = isHover ? COLORS.hover : COLORS.default;
            }
        };

        btn.addEventListener('mouseover', () => handleHover(true));
        btn.addEventListener('mouseout', () => handleHover(false));
        return btn;
    };

    const resetButton = (btn, originalText, originalIcon) => {
        setTimeout(() => {
            btn.innerHTML = `${originalIcon}<span>${originalText}</span>`;
            btn.style.backgroundColor = COLORS.default;
        }, COPY_TIMEOUT);
    };

    const copyToClipboard = async (text, btn, successText, originalIcon) => {
        await navigator.clipboard.writeText(text);
        btn.innerHTML = `${originalIcon}<span>Copied!</span>`;
        resetButton(btn, successText, originalIcon);
    };

    const getTurnstileToken = () => {
        const input = document.querySelector('input[name="cf-turnstile-response"]');
        return input ? input.value : null;
    };

    const handleTokenButton = async (btn) => {
        const token = getTurnstileToken();
        if (token) {
            await copyToClipboard(token, btn, 'Get Token', ICONS.key);
        } else {
            btn.innerHTML = `${ICONS.error}<span>Not Found!</span>`;
            btn.style.backgroundColor = COLORS.error;
            resetButton(btn, 'Get Token', ICONS.key);
        }
    };

    const init = () => {
        addFontLink();
        const container = createButtonContainer();
        const tokenBtn = createButton('Get Token', ICONS.key);

        tokenBtn.addEventListener('click', () => handleTokenButton(tokenBtn));

        container.appendChild(tokenBtn);
        document.body.appendChild(container);
    };

    init();
})();
