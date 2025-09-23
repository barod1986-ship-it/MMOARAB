/**
 * Frontend JavaScript for MOMARAB CORE plugin.
 * General frontend functionality.
 */

(function($) {
    'use strict';

    // Plugin namespace
    window.McpFrontend = window.McpFrontend || {};

    /**
     * Initialize frontend functionality
     */
    McpFrontend.init = function() {
        this.initLazyLoading();
        this.initImageLightbox();
        this.initRatingAnimations();
        this.initTooltips();
    };

    /**
     * Initialize lazy loading for images
     */
    McpFrontend.initLazyLoading = function() {
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        if (img.dataset.src) {
                            img.src = img.dataset.src;
                            img.removeAttribute('data-src');
                        }
                        observer.unobserve(img);
                    }
                });
            });

            document.querySelectorAll('img[data-src]').forEach(img => {
                imageObserver.observe(img);
            });
        }
    };

    /**
     * Initialize image lightbox functionality
     */
    McpFrontend.initImageLightbox = function() {
        // Simple lightbox implementation
        $(document).on('click', '.mcp-gallery-link', function(e) {
            e.preventDefault();
            
            const imageUrl = $(this).attr('href');
            const alt = $(this).find('img').attr('alt') || '';
            
            // Create lightbox overlay
            const lightbox = $(`
                <div class="mcp-lightbox-overlay">
                    <div class="mcp-lightbox-content">
                        <img src="${imageUrl}" alt="${alt}" />
                        <button class="mcp-lightbox-close">&times;</button>
                    </div>
                </div>
            `);
            
            // Add to body
            $('body').append(lightbox);
            
            // Show lightbox
            lightbox.fadeIn(300);
            
            // Close on overlay click or close button
            lightbox.on('click', function(e) {
                if (e.target === this || $(e.target).hasClass('mcp-lightbox-close')) {
                    lightbox.fadeOut(300, function() {
                        lightbox.remove();
                    });
                }
            });
            
            // Close on escape key
            $(document).on('keyup.lightbox', function(e) {
                if (e.keyCode === 27) {
                    lightbox.fadeOut(300, function() {
                        lightbox.remove();
                    });
                    $(document).off('keyup.lightbox');
                }
            });
        });
    };

    /**
     * Initialize rating circle animations
     */
    McpFrontend.initRatingAnimations = function() {
        const ratingCircles = document.querySelectorAll('.mcp-circle-progress');
        
        if ('IntersectionObserver' in window && ratingCircles.length > 0) {
            const circleObserver = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const circle = entry.target;
                        const rating = parseFloat(circle.dataset.rating) || 0;
                        
                        // Animate the circle
                        circle.style.setProperty('--rating', rating);
                        circle.classList.add('animated');
                        
                        circleObserver.unobserve(circle);
                    }
                });
            });

            ratingCircles.forEach(circle => {
                circleObserver.observe(circle);
            });
        }
    };

    /**
     * Initialize tooltips
     */
    McpFrontend.initTooltips = function() {
        // Simple tooltip implementation
        $(document).on('mouseenter', '[data-tooltip]', function() {
            const $this = $(this);
            const tooltipText = $this.data('tooltip');
            
            if (tooltipText) {
                const tooltip = $(`<div class="mcp-tooltip">${tooltipText}</div>`);
                $('body').append(tooltip);
                
                const offset = $this.offset();
                const elementHeight = $this.outerHeight();
                const tooltipWidth = tooltip.outerWidth();
                const tooltipHeight = tooltip.outerHeight();
                
                tooltip.css({
                    top: offset.top - tooltipHeight - 10,
                    left: offset.left + ($this.outerWidth() / 2) - (tooltipWidth / 2)
                });
                
                tooltip.fadeIn(200);
                
                $this.data('tooltip-element', tooltip);
            }
        });
        
        $(document).on('mouseleave', '[data-tooltip]', function() {
            const tooltip = $(this).data('tooltip-element');
            if (tooltip) {
                tooltip.fadeOut(200, function() {
                    tooltip.remove();
                });
                $(this).removeData('tooltip-element');
            }
        });
    };

    /**
     * Utility function to show loading state
     */
    McpFrontend.showLoading = function(container) {
        const $container = $(container);
        const loadingHtml = '<div class="mcp-loading"><span>' + (window.mcpStrings?.loading || 'Loading...') + '</span></div>';
        
        $container.html(loadingHtml);
    };

    /**
     * Utility function to show error message
     */
    McpFrontend.showError = function(container, message) {
        const $container = $(container);
        const errorHtml = `<div class="mcp-error"><p>${message}</p></div>`;
        
        $container.html(errorHtml);
    };

    /**
     * Utility function to format rating display
     */
    McpFrontend.formatRating = function(rating) {
        if (!rating || rating <= 0) {
            return '';
        }
        
        return parseFloat(rating).toFixed(1);
    };

    /**
     * Utility function to truncate text
     */
    McpFrontend.truncateText = function(text, maxLength) {
        if (!text || text.length <= maxLength) {
            return text;
        }
        
        return text.substring(0, maxLength).trim() + '...';
    };

    /**
     * Utility function to escape HTML
     */
    McpFrontend.escapeHtml = function(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    // Initialize when document is ready
    $(document).ready(function() {
        McpFrontend.init();
    });

})(jQuery);

// Add lightbox styles dynamically
(function() {
    const lightboxStyles = `
        <style>
        .mcp-lightbox-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.9);
            z-index: 9999;
            display: none;
            align-items: center;
            justify-content: center;
        }
        
        .mcp-lightbox-content {
            position: relative;
            max-width: 90%;
            max-height: 90%;
        }
        
        .mcp-lightbox-content img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }
        
        .mcp-lightbox-close {
            position: absolute;
            top: -40px;
            right: 0;
            background: none;
            border: none;
            color: white;
            font-size: 30px;
            cursor: pointer;
            padding: 5px 10px;
            line-height: 1;
        }
        
        .mcp-lightbox-close:hover {
            opacity: 0.7;
        }
        
        .mcp-tooltip {
            position: absolute;
            background: #333;
            color: white;
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 12px;
            z-index: 1000;
            display: none;
            white-space: nowrap;
        }
        
        .mcp-tooltip::after {
            content: '';
            position: absolute;
            top: 100%;
            left: 50%;
            margin-left: -5px;
            border-width: 5px;
            border-style: solid;
            border-color: #333 transparent transparent transparent;
        }
        
        .mcp-circle-progress.animated {
            transition: all 1s ease-in-out;
        }
        </style>
    `;
    
    document.head.insertAdjacentHTML('beforeend', lightboxStyles);
})();
