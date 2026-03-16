$(function() {
  $('.direction-container a').click(function() {

    // Check for active
    $('.direction-container a').removeClass('active');
    $(this).addClass('active');

    // Display active tab
    let currentTab = $(this).attr('href');
    $('.content table').hide();
    $(currentTab).show();

    return false;
  });
});