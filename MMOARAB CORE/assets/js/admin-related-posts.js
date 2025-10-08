/**
 * MMOARAB Core - Related Posts Autocomplete
 * Autocomplete للربط بين المقالات والألعاب
 */

(function($) {
    'use strict';
    
    if (typeof $.fn.autocomplete === 'undefined') {
        return;
    }
    
    let searchTimer;
    
    const i18n = window.mcpAjax || {};
    
    $('#mcp_game_search').autocomplete({
        source: function(request, response) {
            // Debounce: انتظر 300ms قبل الإرسال
            clearTimeout(searchTimer);
            searchTimer = setTimeout(function() {
                $.ajax({
                    url: i18n.ajax_url,
                    type: 'GET',
                    dataType: 'json',
                    data: {
                        action: 'mcp_search_games',
                        term: request.term,
                        nonce: i18n.nonce
                    },
                    success: function(data) {
                        if (data.success === false) {
                            response([]);
                            if (data.data && data.data.message) {
                                console.error('MCP Search Error:', data.data.message);
                            }
                        } else {
                            response(data);
                        }
                    },
                    error: function() {
                        response([]);
                    }
                });
            }, 300);
        },
        minLength: 2,
        select: function(event, ui) {
            $('#mcp_related_game_id').val(ui.item.id);
            $('#mcp_game_search').val(ui.item.label);
            
            const selectedText = i18n.selected || 'Selected:';
            const clearText = i18n.clear || 'Clear';
            
            if ($('.mcp-selected-game').length === 0) {
                const $label = $('<strong>').text(ui.item.label);
                const $clear = $('<button type="button" class="button-link-delete" id="mcp-clear-game">').text(clearText);
                const $selected = $('<p class="mcp-selected-game">').text(selectedText + ' ').append($label).append(' ').append($clear);
                $('.mcp-related-game-field').append($selected);
            } else {
                $('.mcp-selected-game strong').text(ui.item.label);
            }
            
            return false;
        }
    });
    
    // Clear selection
    $(document).on('click', '#mcp-clear-game', function(e) {
        e.preventDefault();
        $('#mcp_related_game_id').val('');
        $('#mcp_game_search').val('');
        $('.mcp-selected-game').remove();
    });
    
})(jQuery);
