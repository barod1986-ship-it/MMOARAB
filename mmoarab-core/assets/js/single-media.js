/**
 * Single game media JavaScript for MOMARAB CORE plugin.
 * Handles YouTube videos and image gallery.
 */

(function($) {
    'use strict';

    // Media namespace
    window.McpMedia = window.McpMedia || {};

    /**
     * Initialize media functionality
     */
    McpMedia.init = function() {
        this.initYouTubeVideos();
        this.initImageGallery();
        this.initMediaLightbox();
    };

    /**
     * Initialize YouTube video handling
     */
    McpMedia.initYouTubeVideos = function() {
        const videos = document.querySelectorAll('.mcp-youtube-video iframe');
        
        videos.forEach(function(iframe) {
            // Add loading attribute for better performance
            iframe.setAttribute('loading', 'lazy');
            
            // Optional: Add play button overlay for better UX
            const wrapper = iframe.closest('.mcp-video-wrapper');
            if (wrapper && !wrapper.querySelector('.mcp-play-overlay')) {
                McpMedia.addPlayOverlay(wrapper, iframe);
            }
        });
    };

    /**
     * Add play overlay to video
     */
    McpMedia.addPlayOverlay = function(wrapper, iframe) {
        const overlay = document.createElement('div');
        overlay.className = 'mcp-play-overlay';
        overlay.innerHTML = '<div class="mcp-play-button">▶</div>';
        
        // Get video thumbnail from YouTube
        const src = iframe.src;
        const videoId = McpMedia.extractYouTubeId(src);
        
        if (videoId) {
            overlay.style.backgroundImage = `url(https://img.youtube.com/vi/${videoId}/maxresdefault.jpg)`;
            overlay.style.backgroundSize = 'cover';
            overlay.style.backgroundPosition = 'center';
        }
        
        // Hide iframe initially
        iframe.style.display = 'none';
        
        // Add click handler
        overlay.addEventListener('click', function() {
            iframe.style.display = 'block';
            overlay.style.display = 'none';
            
            // Auto-play video
            const autoplaySrc = iframe.src + (iframe.src.includes('?') ? '&' : '?') + 'autoplay=1';
            iframe.src = autoplaySrc;
        });
        
        wrapper.appendChild(overlay);
    };

    /**
     * Extract YouTube video ID from URL
     */
    McpMedia.extractYouTubeId = function(url) {
        const regExp = /^.*((youtu.be\/)|(v\/)|(\/u\/\w\/)|(embed\/)|(watch\?))\??v?=?([^#&?]*).*/;
        const match = url.match(regExp);
        return (match && match[7].length === 11) ? match[7] : null;
    };

    /**
     * Initialize image gallery
     */
    McpMedia.initImageGallery = function() {
        const galleryItems = document.querySelectorAll('.mcp-gallery-item');
        
        galleryItems.forEach(function(item, index) {
            const link = item.querySelector('.mcp-gallery-link');
            if (link) {
                link.addEventListener('click', function(e) {
                    e.preventDefault();
                    McpMedia.openGalleryLightbox(galleryItems, index);
                });
            }
        });
    };

    /**
     * Initialize media lightbox
     */
    McpMedia.initMediaLightbox = function() {
        // This is handled by the gallery initialization
        // Additional lightbox features can be added here
    };

    /**
     * Open gallery lightbox
     */
    McpMedia.openGalleryLightbox = function(galleryItems, startIndex) {
        const lightbox = McpMedia.createLightbox();
        const images = Array.from(galleryItems).map(item => {
            const link = item.querySelector('.mcp-gallery-link');
            const img = item.querySelector('img');
            const caption = item.querySelector('.mcp-gallery-caption');
            
            return {
                src: link.href,
                alt: img.alt || '',
                caption: caption ? caption.textContent : ''
            };
        });

        McpMedia.showLightboxImage(lightbox, images, startIndex);
        document.body.appendChild(lightbox);
        
        // Show lightbox
        setTimeout(() => {
            lightbox.classList.add('active');
        }, 10);
    };

    /**
     * Create lightbox element
     */
    McpMedia.createLightbox = function() {
        const lightbox = document.createElement('div');
        lightbox.className = 'mcp-media-lightbox';
        lightbox.innerHTML = `
            <div class="mcp-lightbox-backdrop"></div>
            <div class="mcp-lightbox-container">
                <div class="mcp-lightbox-content">
                    <img class="mcp-lightbox-image" src="" alt="" />
                    <div class="mcp-lightbox-caption"></div>
                </div>
                <div class="mcp-lightbox-controls">
                    <button class="mcp-lightbox-prev" aria-label="Previous image">‹</button>
                    <button class="mcp-lightbox-next" aria-label="Next image">›</button>
                    <button class="mcp-lightbox-close" aria-label="Close lightbox">×</button>
                </div>
                <div class="mcp-lightbox-counter">
                    <span class="mcp-current">1</span> / <span class="mcp-total">1</span>
                </div>
            </div>
        `;

        return lightbox;
    };

    /**
     * Show image in lightbox
     */
    McpMedia.showLightboxImage = function(lightbox, images, index) {
        const img = lightbox.querySelector('.mcp-lightbox-image');
        const caption = lightbox.querySelector('.mcp-lightbox-caption');
        const current = lightbox.querySelector('.mcp-current');
        const total = lightbox.querySelector('.mcp-total');
        const prevBtn = lightbox.querySelector('.mcp-lightbox-prev');
        const nextBtn = lightbox.querySelector('.mcp-lightbox-next');
        const closeBtn = lightbox.querySelector('.mcp-lightbox-close');
        const backdrop = lightbox.querySelector('.mcp-lightbox-backdrop');

        const currentImage = images[index];
        
        // Update image
        img.src = currentImage.src;
        img.alt = currentImage.alt;
        
        // Update caption
        caption.textContent = currentImage.caption;
        caption.style.display = currentImage.caption ? 'block' : 'none';
        
        // Update counter
        current.textContent = index + 1;
        total.textContent = images.length;
        
        // Show/hide navigation buttons
        prevBtn.style.display = images.length > 1 ? 'block' : 'none';
        nextBtn.style.display = images.length > 1 ? 'block' : 'none';
        
        // Event handlers
        const closeLightbox = () => {
            lightbox.classList.remove('active');
            setTimeout(() => {
                if (lightbox.parentNode) {
                    lightbox.parentNode.removeChild(lightbox);
                }
            }, 300);
        };

        const showPrev = () => {
            const newIndex = index > 0 ? index - 1 : images.length - 1;
            McpMedia.showLightboxImage(lightbox, images, newIndex);
        };

        const showNext = () => {
            const newIndex = index < images.length - 1 ? index + 1 : 0;
            McpMedia.showLightboxImage(lightbox, images, newIndex);
        };

        // Remove existing event listeners
        const newCloseBtn = closeBtn.cloneNode(true);
        const newPrevBtn = prevBtn.cloneNode(true);
        const newNextBtn = nextBtn.cloneNode(true);
        const newBackdrop = backdrop.cloneNode(true);

        closeBtn.parentNode.replaceChild(newCloseBtn, closeBtn);
        prevBtn.parentNode.replaceChild(newPrevBtn, prevBtn);
        nextBtn.parentNode.replaceChild(newNextBtn, nextBtn);
        backdrop.parentNode.replaceChild(newBackdrop, backdrop);

        // Add event listeners
        newCloseBtn.addEventListener('click', closeLightbox);
        newBackdrop.addEventListener('click', closeLightbox);
        newPrevBtn.addEventListener('click', showPrev);
        newNextBtn.addEventListener('click', showNext);

        // Keyboard navigation
        const handleKeydown = (e) => {
            switch (e.key) {
                case 'Escape':
                    closeLightbox();
                    break;
                case 'ArrowLeft':
                    if (images.length > 1) showPrev();
                    break;
                case 'ArrowRight':
                    if (images.length > 1) showNext();
                    break;
            }
        };

        document.addEventListener('keydown', handleKeydown);
        
        // Clean up keyboard listener when lightbox closes
        const originalClose = closeLightbox;
        const closeLightboxWithCleanup = () => {
            document.removeEventListener('keydown', handleKeydown);
            originalClose();
        };

        newCloseBtn.onclick = closeLightboxWithCleanup;
        newBackdrop.onclick = closeLightboxWithCleanup;
    };

    /**
     * Preload images for better performance
     */
    McpMedia.preloadImages = function(images) {
        images.forEach(function(imageData) {
            const img = new Image();
            img.src = imageData.src;
        });
    };

    // Initialize when document is ready
    $(document).ready(function() {
        if ($('.mcp-game-media').length > 0) {
            McpMedia.init();
        }
    });

})(jQuery);

// Add media lightbox styles
(function() {
    const mediaStyles = `
        <style>
        .mcp-media-lightbox {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 10000;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s ease, visibility 0.3s ease;
        }
        
        .mcp-media-lightbox.active {
            opacity: 1;
            visibility: visible;
        }
        
        .mcp-lightbox-backdrop {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.9);
        }
        
        .mcp-lightbox-container {
            position: relative;
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            box-sizing: border-box;
        }
        
        .mcp-lightbox-content {
            position: relative;
            max-width: 90%;
            max-height: 90%;
            text-align: center;
        }
        
        .mcp-lightbox-image {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            border-radius: 8px;
        }
        
        .mcp-lightbox-caption {
            margin-top: 15px;
            color: white;
            font-size: 16px;
            line-height: 1.4;
        }
        
        .mcp-lightbox-controls {
            position: absolute;
            top: 20px;
            right: 20px;
        }
        
        .mcp-lightbox-controls button {
            background: rgba(0, 0, 0, 0.7);
            border: none;
            color: white;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            font-size: 24px;
            cursor: pointer;
            margin-left: 10px;
            transition: background 0.3s ease;
        }
        
        .mcp-lightbox-controls button:hover {
            background: rgba(0, 0, 0, 0.9);
        }
        
        .mcp-lightbox-prev,
        .mcp-lightbox-next {
            position: absolute;
            top: 50%;
            transform: translateY(-50%);
            background: rgba(0, 0, 0, 0.7);
            border: none;
            color: white;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            font-size: 30px;
            cursor: pointer;
            transition: background 0.3s ease;
        }
        
        .mcp-lightbox-prev {
            left: 20px;
        }
        
        .mcp-lightbox-next {
            right: 20px;
        }
        
        .mcp-lightbox-prev:hover,
        .mcp-lightbox-next:hover {
            background: rgba(0, 0, 0, 0.9);
        }
        
        .mcp-lightbox-counter {
            position: absolute;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            color: white;
            background: rgba(0, 0, 0, 0.7);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 14px;
        }
        
        .mcp-play-overlay {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: background 0.3s ease;
        }
        
        .mcp-play-overlay:hover {
            background: rgba(0, 0, 0, 0.5);
        }
        
        .mcp-play-button {
            width: 80px;
            height: 80px;
            background: rgba(255, 255, 255, 0.9);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 30px;
            color: #333;
            transition: transform 0.3s ease;
        }
        
        .mcp-play-overlay:hover .mcp-play-button {
            transform: scale(1.1);
        }
        
        @media (max-width: 768px) {
            .mcp-lightbox-prev,
            .mcp-lightbox-next {
                width: 50px;
                height: 50px;
                font-size: 24px;
            }
            
            .mcp-lightbox-controls button {
                width: 40px;
                height: 40px;
                font-size: 20px;
            }
            
            .mcp-play-button {
                width: 60px;
                height: 60px;
                font-size: 24px;
            }
        }
        </style>
    `;
    
    document.head.insertAdjacentHTML('beforeend', mediaStyles);
})();
