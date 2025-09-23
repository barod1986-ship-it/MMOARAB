/**
 * Select2 initialization for MOMARAB CORE plugin.
 * Handles Select2 for related game selection in posts.
 */

(function($) {
    'use strict';

    // Select2 namespace
    window.McpSelect2 = window.McpSelect2 || {};

    /**
     * Initialize Select2 functionality
     */
    McpSelect2.init = function() {
        this.initRelatedGameSelect();
    };

    /**
     * Initialize related game Select2
     */
    McpSelect2.initRelatedGameSelect = function() {
        const $select = $('#mcp_related_game_select');
        
        if ($select.length === 0) {
            return;
        }

        $select.select2({
            ajax: {
                url: ajaxurl,
                dataType: 'json',
                delay: 250,
                data: function(params) {
                    return {
                        q: params.term,
                        action: 'mcp_search_games',
                        nonce: window.mcpSelect2?.nonce || ''
                    };
                },
                processResults: function(data) {
                    if (data.success && data.data) {
                        return {
                            results: data.data
                        };
                    }
                    return {
                        results: []
                    };
                },
                cache: true
            },
            placeholder: window.mcpSelect2?.strings?.placeholder || 'اختر لعبة...',
            allowClear: true,
            minimumInputLength: 2,
            language: {
                inputTooShort: function() {
                    return window.mcpSelect2?.strings?.input_too_short || 'يرجى إدخال حرفين على الأقل';
                },
                noResults: function() {
                    return window.mcpSelect2?.strings?.no_results || 'لم يتم العثور على نتائج';
                },
                searching: function() {
                    return window.mcpSelect2?.strings?.searching || 'جاري البحث...';
                },
                loadingMore: function() {
                    return window.mcpSelect2?.strings?.loading_more || 'جاري تحميل المزيد...';
                }
            },
            escapeMarkup: function(markup) {
                return markup;
            },
            templateResult: function(game) {
                if (game.loading) {
                    return game.text;
                }

                // Custom template for search results
                const $result = $(
                    '<div class="mcp-select2-result">' +
                        '<div class="mcp-game-title">' + McpSelect2.escapeHtml(game.text) + '</div>' +
                    '</div>'
                );

                return $result;
            },
            templateSelection: function(game) {
                return game.text || game.id;
            }
        });

        // Handle selection events
        $select.on('select2:select', function(e) {
            const data = e.params.data;
            
            // Trigger custom event
            $(document).trigger('mcpGameSelected', [data]);
        });

        $select.on('select2:unselect', function(e) {
            
            // Trigger custom event
            $(document).trigger('mcpGameUnselected');
        });

        // Error handling
        $select.on('select2:open', function() {
            // Add custom CSS class for styling
            $('.select2-dropdown').addClass('mcp-select2-dropdown');
        });
    };

    /**
     * Escape HTML to prevent XSS
     */
    McpSelect2.escapeHtml = function(text) {
        if (!text) return '';
        
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    /**
     * Refresh Select2 options
     */
    McpSelect2.refresh = function() {
        $('#mcp_related_game_select').select2('destroy');
        this.initRelatedGameSelect();
    };

    /**
     * Set selected value programmatically
     */
    McpSelect2.setSelected = function(gameId, gameTitle) {
        const $select = $('#mcp_related_game_select');
        
        if ($select.length === 0) {
            return;
        }

        // Create option if it doesn't exist
        if ($select.find('option[value="' + gameId + '"]').length === 0) {
            const newOption = new Option(gameTitle, gameId, true, true);
            $select.append(newOption);
        } else {
            $select.val(gameId);
        }

        $select.trigger('change');
    };

    /**
     * Clear selection
     */
    McpSelect2.clearSelection = function() {
        $('#mcp_related_game_select').val(null).trigger('change');
    };

    /**
     * Get current selection
     */
    McpSelect2.getSelection = function() {
        const $select = $('#mcp_related_game_select');
        const selectedData = $select.select2('data');
        
        if (selectedData && selectedData.length > 0) {
            return {
                id: selectedData[0].id,
                text: selectedData[0].text
            };
        }
        
        return null;
    };

    // Initialize when document is ready
    $(document).ready(function() {
        // Only initialize on post edit screens
        if ($('body').hasClass('post-type-post') && $('#mcp_related_game_select').length > 0) {
            McpSelect2.init();
        }
    });

    // Handle WordPress media modal conflicts
    $(document).on('DOMNodeInserted', '.media-modal', function() {
        // Ensure Select2 dropdowns work in media modals
        $('.select2-container').css('z-index', 999999);
    });

})(jQuery);

// Add Select2 custom styles
(function() {
    const select2Styles = `
        <style>
        .mcp-select2-dropdown {
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        
        .mcp-select2-result {
            padding: 8px 12px;
        }
        
        .mcp-game-title {
            font-weight: 500;
            color: #333;
        }
        
        .select2-container--default .select2-results__option--highlighted[aria-selected] .mcp-game-title {
            color: white;
        }
        
        .select2-container--default .select2-selection--single {
            border: 1px solid #ddd;
            border-radius: 4px;
            height: auto;
            padding: 6px 12px;
        }
        
        .select2-container--default .select2-selection--single .select2-selection__rendered {
            color: #333;
            line-height: 1.4;
            padding: 0;
        }
        
        .select2-container--default .select2-selection--single .select2-selection__arrow {
            height: 34px;
            right: 8px;
        }
        
        .select2-container--default .select2-selection--single:focus {
            border-color: #0073aa;
            box-shadow: 0 0 0 1px #0073aa;
        }
        
        .select2-container--default .select2-search--dropdown .select2-search__field {
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 8px 12px;
        }
        
        .select2-container--default .select2-results__option {
            padding: 8px 12px;
        }
        
        .select2-container--default .select2-results__option[aria-selected=true] {
            background-color: #0073aa;
            color: white;
        }
        
        .select2-container--default .select2-results__option--highlighted[aria-selected] {
            background-color: #005177;
        }
        
        /* RTL Support */
        [dir="rtl"] .select2-container--default .select2-selection--single .select2-selection__arrow {
            left: 8px;
            right: auto;
        }
        
        [dir="rtl"] .select2-container--default .select2-selection--single .select2-selection__rendered {
            padding-right: 0;
            padding-left: 20px;
        }
        </style>
    `;
    
    document.head.insertAdjacentHTML('beforeend', select2Styles);
})();
