/**
 * MMOARAB Core - Lightbox
 * معرض الصور مع Lightbox تفاعلي
 */

(function($) {
    'use strict';
    
    let currentIndex = 0;
    let images = [];
    
    // Initialize Lightbox
    function initLightbox() {
        // Create lightbox HTML if not exists
        if ($('.mcp-lightbox').length === 0) {
            $('body').append(`
                <div class="mcp-lightbox">
                    <button class="mcp-lightbox-close" aria-label="Close">&times;</button>
                    <button class="mcp-lightbox-prev" aria-label="Previous">&larr;</button>
                    <button class="mcp-lightbox-next" aria-label="Next">&rarr;</button>
                    <div class="mcp-lightbox-content">
                        <img class="mcp-lightbox-image" src="" alt="">
                    </div>
                </div>
            `);
        }
        
        // Collect all gallery images
        $('.mcp-gallery-item').each(function(index) {
            const img = $(this).find('img');
            images.push({
                src: img.data('full') || img.attr('src'),
                alt: img.attr('alt') || ''
            });
            
            $(this).attr('data-index', index);
        });
    }
    
    // Open Lightbox
    function openLightbox(index) {
        currentIndex = index;
        updateLightboxImage();
        $('.mcp-lightbox').addClass('active');
        $('body').css('overflow', 'hidden');
    }
    
    // Close Lightbox
    function closeLightbox() {
        $('.mcp-lightbox').removeClass('active');
        $('body').css('overflow', '');
    }
    
    // Update Image
    function updateLightboxImage() {
        if (images[currentIndex]) {
            $('.mcp-lightbox-image')
                .attr('src', images[currentIndex].src)
                .attr('alt', images[currentIndex].alt);
        }
    }
    
    // Next Image
    function nextImage() {
        currentIndex = (currentIndex + 1) % images.length;
        updateLightboxImage();
    }
    
    // Previous Image
    function prevImage() {
        currentIndex = (currentIndex - 1 + images.length) % images.length;
        updateLightboxImage();
    }
    
    // Event Handlers
    $(function() {
        initLightbox();
        
        // Click on gallery item
        $('.mcp-gallery-item').on('click', function() {
            const index = parseInt($(this).attr('data-index'));
            openLightbox(index);
        });
        
        // Close button
        $('.mcp-lightbox-close').on('click', closeLightbox);
        
        // Next button
        $('.mcp-lightbox-next').on('click', nextImage);
        
        // Previous button
        $('.mcp-lightbox-prev').on('click', prevImage);
        
        // Click outside image
        $('.mcp-lightbox').on('click', function(e) {
            if ($(e.target).hasClass('mcp-lightbox')) {
                closeLightbox();
            }
        });
        
        // Keyboard navigation
        $(document).on('keydown', function(e) {
            if (!$('.mcp-lightbox').hasClass('active')) {
                return;
            }
            
            switch(e.key) {
                case 'Escape':
                    closeLightbox();
                    break;
                case 'ArrowRight':
                    nextImage();
                    break;
                case 'ArrowLeft':
                    prevImage();
                    break;
            }
        });
    });
    
})(jQuery);
