/**
 * Archive filter JavaScript for MOMARAB CORE plugin.
 * Handles Ajax filtering and URL updates.
 */

(function($) {
    'use strict';

    // Filter namespace
    window.McpFilter = window.McpFilter || {};

    /**
     * Initialize filter functionality
     */
    McpFilter.init = function() {
        this.bindEvents();
        this.initializeFromURL();
    };

    /**
     * Bind filter events
     */
    McpFilter.bindEvents = function() {
        const self = this;

        // Form submission
        $(document).on('submit', '.mcp-filter-controls', function(e) {
            e.preventDefault();
            self.performFilter();
        });

        // Filter select changes
        $(document).on('change', '.mcp-filter-select', function() {
            self.performFilter();
        });

        // Reset button
        $(document).on('click', '.mcp-filter-reset', function(e) {
            e.preventDefault();
            self.resetFilters();
        });

        // Browser back/forward
        $(window).on('popstate', function() {
            self.initializeFromURL();
        });
    };

    /**
     * Initialize filters from current URL
     */
    McpFilter.initializeFromURL = function() {
        const urlParams = new URLSearchParams(window.location.search);
        
        // Set form values from URL
        $('.mcp-filter-select').each(function() {
            const $select = $(this);
            const paramName = $select.attr('name');
            const paramValue = urlParams.get(paramName);
            
            if (paramValue) {
                $select.val(paramValue);
            }
        });

        // Perform initial filter if we have parameters
        if (urlParams.toString()) {
            this.performFilter(false); // Don't update URL
        }
    };

    /**
     * Perform Ajax filter
     */
    McpFilter.performFilter = function(updateURL = true) {
        const self = this;
        const $form = $('.mcp-filter-controls');
        const $results = $('#mcp-filter-results');
        const $loading = $('#mcp-filter-loading');

        // Show loading
        $loading.show();
        $results.hide();

        // Collect form data
        const formData = this.collectFormData($form);

        // Add nonce
        formData.nonce = window.mcpAjax?.nonce || '';
        formData.action = 'mcp_filter_games';

        // Perform Ajax request
        $.ajax({
            url: window.mcpAjax?.ajaxurl || '/wp-admin/admin-ajax.php',
            type: 'POST',
            data: formData,
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    self.displayResults(response.data);
                    
                    if (updateURL) {
                        self.updateURL(formData);
                    }
                } else {
                    self.displayError(response.data?.message || window.mcpAjax?.strings?.error || 'An error occurred');
                }
            },
            error: function() {
                self.displayError(window.mcpAjax?.strings?.error || 'An error occurred');
            },
            complete: function() {
                $loading.hide();
                $results.show();
            }
        });
    };

    /**
     * Collect form data
     */
    McpFilter.collectFormData = function($form) {
        const data = {};
        
        $form.find('.mcp-filter-select').each(function() {
            const $select = $(this);
            const name = $select.attr('name');
            const value = $select.val();
            
            if (value && value !== '') {
                data[name] = value;
            }
        });

        return data;
    };

    /**
     * Display filter results
     */
    McpFilter.displayResults = function(data) {
        const $results = $('#mcp-filter-results');
        
        if (!data.games || data.games.length === 0) {
            $results.html('<div class="mcp-no-games"><p>' + (window.mcpAjax?.strings?.no_results || 'No games found') + '</p></div>');
            return;
        }

        let html = '<div class="mcp-games-grid"><div class="mcp-games-list">';
        
        data.games.forEach(function(game) {
            html += McpFilter.renderGameCard(game);
        });
        
        html += '</div></div>';

        // Add pagination if needed
        if (data.pagination && data.pagination.total_pages > 1) {
            html += McpFilter.renderPagination(data.pagination);
        }

        $results.html(html);

        // Trigger custom event
        $(document).trigger('mcpFilterComplete', [data]);
    };

    /**
     * Render individual game card
     */
    McpFilter.renderGameCard = function(game) {
        const thumbnail = game.thumbnail || '';
        const rating = game.rating ? parseFloat(game.rating).toFixed(1) : '';
        const developer = game.developer || '';
        const releaseDate = game.release_date || '';

        let html = '<div class="mcp-game-card">';
        
        // Image
        html += '<div class="mcp-card-image">';
        if (thumbnail) {
            html += `<img src="${McpFilter.escapeHtml(thumbnail)}" alt="${McpFilter.escapeHtml(game.title)}" loading="lazy" />`;
        } else {
            html += '<div class="mcp-placeholder-image"><span>لا توجد صورة</span></div>';
        }
        
        if (rating) {
            html += `<div class="mcp-card-rating"><span class="mcp-rating-value">${rating}</span><span class="mcp-rating-max">/10</span></div>`;
        }
        html += '</div>';

        // Content
        html += '<div class="mcp-card-content">';
        html += `<h3 class="mcp-card-title"><a href="${McpFilter.escapeHtml(game.permalink)}">${McpFilter.escapeHtml(game.title)}</a></h3>`;
        
        if (developer) {
            html += `<p class="mcp-card-developer"><strong>المطوّر:</strong> ${McpFilter.escapeHtml(developer)}</p>`;
        }
        
        if (releaseDate) {
            html += `<p class="mcp-card-date"><strong>تاريخ الإطلاق:</strong> ${McpFilter.escapeHtml(releaseDate)}</p>`;
        }
        
        if (game.excerpt) {
            html += `<div class="mcp-card-excerpt">${game.excerpt}</div>`;
        }

        // Taxonomies
        if (game.taxonomies) {
            html += '<div class="mcp-card-taxonomies">';
            
            ['game_type', 'game_status'].forEach(function(taxonomy) {
                if (game.taxonomies[taxonomy] && game.taxonomies[taxonomy].length > 0) {
                    html += `<div class="mcp-card-tax mcp-card-${taxonomy}">`;
                    game.taxonomies[taxonomy].forEach(function(term) {
                        html += `<span class="mcp-tax-tag">${McpFilter.escapeHtml(term.name)}</span>`;
                    });
                    html += '</div>';
                }
            });
            
            html += '</div>';
        }

        html += '</div></div>';

        return html;
    };

    /**
     * Render pagination
     */
    McpFilter.renderPagination = function(pagination) {
        if (pagination.total_pages <= 1) {
            return '';
        }

        let html = '<div class="mcp-pagination">';
        
        for (let i = 1; i <= pagination.total_pages; i++) {
            const isActive = i === pagination.current_page;
            const className = isActive ? 'page-numbers current' : 'page-numbers';
            
            html += `<span class="${className}" data-page="${i}">${i}</span>`;
        }
        
        html += '</div>';

        return html;
    };

    /**
     * Display error message
     */
    McpFilter.displayError = function(message) {
        const $results = $('#mcp-filter-results');
        $results.html(`<div class="mcp-error"><p>${McpFilter.escapeHtml(message)}</p></div>`);
    };

    /**
     * Reset all filters
     */
    McpFilter.resetFilters = function() {
        $('.mcp-filter-select').val('');
        this.performFilter();
    };

    /**
     * Update browser URL
     */
    McpFilter.updateURL = function(data) {
        const url = new URL(window.location);
        
        // Clear existing filter parameters
        ['type', 'status', 'mode', 'platform', 'sort', 'page'].forEach(function(param) {
            url.searchParams.delete(param);
        });

        // Add new parameters
        Object.keys(data).forEach(function(key) {
            if (key !== 'action' && key !== 'nonce' && data[key]) {
                url.searchParams.set(key, data[key]);
            }
        });

        // Update URL without page reload
        window.history.pushState({}, '', url.toString());
    };

    /**
     * Escape HTML to prevent XSS
     */
    McpFilter.escapeHtml = function(text) {
        if (!text) return '';
        
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    /**
     * Handle pagination clicks
     */
    $(document).on('click', '.mcp-pagination .page-numbers', function(e) {
        e.preventDefault();
        
        if ($(this).hasClass('current')) {
            return;
        }

        const page = $(this).data('page');
        if (page) {
            // Add page to form data and filter
            const $form = $('.mcp-filter-controls');
            const formData = McpFilter.collectFormData($form);
            formData.page = page;
            formData.nonce = window.mcpAjax?.nonce || '';
            formData.action = 'mcp_filter_games';

            // Perform filter with pagination
            McpFilter.performFilterWithData(formData);
        }
    });

    /**
     * Perform filter with specific data
     */
    McpFilter.performFilterWithData = function(formData) {
        const self = this;
        const $results = $('#mcp-filter-results');
        const $loading = $('#mcp-filter-loading');

        $loading.show();
        $results.hide();

        $.ajax({
            url: window.mcpAjax?.ajaxurl || '/wp-admin/admin-ajax.php',
            type: 'POST',
            data: formData,
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    self.displayResults(response.data);
                    self.updateURL(formData);
                    
                    // Scroll to results
                    $('html, body').animate({
                        scrollTop: $('#mcp-filter-results').offset().top - 100
                    }, 500);
                } else {
                    self.displayError(response.data?.message || window.mcpAjax?.strings?.error || 'An error occurred');
                }
            },
            error: function() {
                self.displayError(window.mcpAjax?.strings?.error || 'An error occurred');
            },
            complete: function() {
                $loading.hide();
                $results.show();
            }
        });
    };

    // Initialize when document is ready
    $(document).ready(function() {
        if ($('.mcp-filter-form').length > 0) {
            McpFilter.init();
        }
    });

})(jQuery);
