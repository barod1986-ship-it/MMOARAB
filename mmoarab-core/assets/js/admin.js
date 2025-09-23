jQuery(function($){
  let frame;
  const max = (window.MCP_GALLERY && MCP_GALLERY.max) || 4;

  function render(ids){
    const ul = $('.mcp-gallery-preview').empty();
    ids.forEach(id=>{
      const att = wp.media.attachment(id);
      att.fetch();
      const url = att.get('sizes')?.thumbnail?.url || att.get('url') || '';
      ul.append($('<li>').attr('data-id', id).append($('<img>').attr('src', url)));
    });
    $('#mcp_gallery').val(ids.join(','));
  }

  $('.mcp-gallery-select').on('click', function(e){
    e.preventDefault();
    if (frame) frame.close();
    frame = wp.media({ title:'اختر حتى '+max+' صور', library:{type:'image'}, multiple:true });
    frame.on('open', function(){
      const ids = ($('#mcp_gallery').val() || '').split(',').map(x=>parseInt(x,10)).filter(Boolean);
      const sel = frame.state().get('selection');
      ids.forEach(id=>{ const a = wp.media.attachment(id); a.fetch(); sel.add(a); });
    });
    frame.on('select', function(){
      const ids = frame.state().get('selection').toArray().map(a=>a.get('id'));
      render(Array.from(new Set(ids)).slice(0, max));
    });
    frame.open();
  });

  $('.mcp-gallery-clear').on('click', function(e){
    e.preventDefault();
    render([]);
  });

});
