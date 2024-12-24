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
        link: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512" style="width: 16px; height: 16px; fill: white; margin-right: 8px;"><path d="M579.8 267.7c56.5-56.5 56.5-148 0-204.5c-50-50-128.8-56.5-186.3-15.4l-1.6 1.1c-14.4 10.3-17.7 30.3-7.4 44.6s30.3 17.7 44.6 7.4l1.6-1.1c32.1-22.9 76-19.3 103.8 8.6c31.5 31.5 31.5 82.5 0 114L422.3 334.8c-31.5 31.5-82.5 31.5-114 0c-27.9-27.9-31.5-71.8-8.6-103.8l1.1-1.6c10.3-14.4 6.9-34.4-7.4-44.6s-34.4-6.9-44.6 7.4l-1.1 1.6C206.5 251.2 213 330 263 380c56.5 56.5 148 56.5 204.5 0L579.8 267.7zM60.2 244.3c-56.5 56.5-56.5 148 0 204.5c50 50 128.8 56.5 186.3 15.4l1.6-1.1c14.4-10.3 17.7-30.3 7.4-44.6s-30.3-17.7-44.6-7.4l-1.6 1.1c-32.1 22.9-76 19.3-103.8-8.6C74 372 74 321 105.5 289.5L217.7 177.2c31.5-31.5 82.5-31.5 114 0c27.9 27.9 31.5 71.8 8.6 103.9l-1.1 1.6c-10.3 14.4-6.9 34.4 7.4 44.6s34.4 6.9 44.6-7.4l1.1-1.6C433.5 260.8 427 182 377 132c-56.5-56.5-148-56.5-204.5 0L60.2 244.3z"/></svg>`,
        key: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" style="width: 16px; height: 16px; fill: white; margin-right: 8px;"><path d="M336 352c97.2 0 176-78.8 176-176S433.2 0 336 0S160 78.8 160 176c0 18.7 2.9 36.8 8.3 53.7L7 391c-4.5 4.5-7 10.6-7 17l0 80c0 13.3 10.7 24 24 24l80 0c13.3 0 24-10.7 24-24l0-40 40 0c13.3 0 24-10.7 24-24l0-40 40 0c6.4 0 12.5-2.5 17-7l33.3-33.3c16.9 5.4 35 8.3 53.7 8.3zM376 96a40 40 0 1 1 0 80 40 40 0 1 1 0-80z"/></svg>`,
        error: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" style="width: 16px; height: 16px; fill: white; margin-right: 8px;"><path d="M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zm0-384c13.3 0 24 10.7 24 24l0 112c0 13.3-10.7 24-24 24s-24-10.7-24-24l0-112c0-13.3 10.7-24 24-24zM224 352a32 32 0 1 1 64 0 32 32 0 1 1 -64 0z"/></svg>`
    };

    const SPOTIFY_URLS = [
        "https://open.spotify.com/track/2plbrEY59IikOBgBGLjaoe",
        "https://open.spotify.com/track/4wJ5Qq0jBN4ajy7ouZIV1c",
        "https://open.spotify.com/track/6dOtVTDdiauQNBQEDOtlAB",
        "https://open.spotify.com/track/7uoFMmxln0GPXQ0AcCBXRq",
        "https://open.spotify.com/track/2HRqTpkrJO5ggZyyK6NPWz"
    ];

    const getRandomUrl = () => SPOTIFY_URLS[Math.floor(Math.random() * SPOTIFY_URLS.length)];
    
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
        const urlBtn = createButton('Get URL', ICONS.link);
        const tokenBtn = createButton('Get Token', ICONS.key);

        urlBtn.addEventListener('click', () => copyToClipboard(getRandomUrl(), urlBtn, 'Get URL', ICONS.link));
        tokenBtn.addEventListener('click', () => handleTokenButton(tokenBtn));

        container.append(urlBtn, tokenBtn);
        document.body.appendChild(container);
    };

    init();
})();
