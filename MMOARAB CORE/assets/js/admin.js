/**
 * MMOARAB Core - Admin JavaScript
 * Gallery Management + Overall Rating Calculator
 */

(function($) {
    'use strict';
    
    // Gallery Management
    let galleryFrame;
    
    // استخدام event delegation بسيط
    $(document).on('click', '#mcp-add-gallery-images', function(e) {
        e.preventDefault();
        
        if (galleryFrame) {
            galleryFrame.open();
            return;
        }
        
        // استخدام النصوص المترجمة
        const i18n = window.mcpI18n || {};
        
        galleryFrame = wp.media({
            title: i18n.selectGalleryImages || 'Select Gallery Images',
            button: {
                text: i18n.addToGallery || 'Add to Gallery'
            },
            multiple: true
        });
        
        galleryFrame.on('select', function() {
            const selection = galleryFrame.state().get('selection');
            const ids = $('#mcp_gallery').val() ? $('#mcp_gallery').val().split(',') : [];
            
            selection.map(function(attachment) {
                attachment = attachment.toJSON();
                
                if (ids.indexOf(attachment.id.toString()) === -1) {
                    ids.push(attachment.id);
                    
                    // Escape URLs و إضافة alt text مناسب
                    const thumbnailUrl = attachment.sizes && attachment.sizes.thumbnail 
                        ? $('<div>').text(attachment.sizes.thumbnail.url).html()
                        : $('<div>').text(attachment.url).html();
                    
                    const altText = attachment.alt || attachment.title || (i18n.galleryImageAlt || 'Gallery Image');
                    
                    const imageHtml = `
                        <div class="mcp-gallery-image" data-id="${attachment.id}">
                            <img src="${thumbnailUrl}" alt="${$('<div>').text(altText).html()}">
                            <button type="button" class="mcp-remove-image">×</button>
                        </div>
                    `;
                    
                    $('#mcp-gallery-images').append(imageHtml);
                }
            });
            
            $('#mcp_gallery').val(ids.join(','));
        });
        
        galleryFrame.open();
    });
    
    // Remove Image
    $(document).on('click', '.mcp-remove-image', function(e) {
        e.preventDefault();
        const $item = $(this).closest('.mcp-gallery-image');
        const imageId = $item.data('id');
        
        $item.remove();
        updateGalleryInput();
    });
    
    // Make Gallery Sortable
    if ($.fn.sortable) {
        $('#mcp-gallery-images').sortable({
            update: function() {
                updateGalleryInput();
            }
        });
    }
    
    function updateGalleryInput() {
        const ids = [];
        $('#mcp-gallery-images .mcp-gallery-image').each(function() {
            ids.push($(this).data('id'));
        });
        $('#mcp_gallery').val(ids.join(','));
    }
    
    // Calculate Overall Rating
    function calculateOverall() {
        const ratings = [];
        
        $('.mcp-rating-input').each(function() {
            const val = parseFloat($(this).val());
            if (!isNaN(val) && val >= 1 && val <= 10) {
                ratings.push(val);
            }
        });
        
        if (ratings.length > 0) {
            const sum = ratings.reduce((a, b) => a + b, 0);
            const avg = (sum / ratings.length).toFixed(1);
            $('#mcp_rating_overall').val(avg);
        } else {
            $('#mcp_rating_overall').val('');
        }
    }
    
    $('.mcp-rating-input').on('input change', function() {
        calculateOverall();
    });
    
    // Calculate on page load
    calculateOverall();
    
    // Seed Terms AJAX (only on dashboard page)
    if (typeof mcpAdmin !== 'undefined') {
        const i18n = window.mcpI18n || {};
        
        $('#mcp-add-seed-terms').on('click', function() {
            const $button = $(this);
            const $message = $('#mcp-seed-terms-message');
            const originalText = $button.text();
            
            $button.prop('disabled', true).text(i18n.addingTerms || 'Adding...');
            $message.removeClass('success error').html('');
            
            $.ajax({
                url: mcpAdmin.ajax_url,
                type: 'POST',
                data: {
                    action: 'mcp_add_seed_terms',
                    nonce: mcpAdmin.nonce
                },
                success: function(response) {
                    if (response.success) {
                        $message.addClass('success').html(response.data.message);
                    } else {
                        $message.addClass('error').html(response.data.message);
                    }
                    $button.prop('disabled', false).text(originalText);
                },
                error: function() {
                    $message.addClass('error').html(i18n.errorOccurred || 'An error occurred. Please try again.');
                    $button.prop('disabled', false).text(originalText);
                }
            });
        });
    }
    
})(jQuery);
