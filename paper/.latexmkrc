@default_files = ('main.tex');
$pdf_mode = 5;
$out_dir = 'build';
$xelatex = 'xelatex -synctex=1 %O %S';
$ENV{'TEXINPUTS'} = './template/upstream//:' . ($ENV{'TEXINPUTS'} // '');
$ENV{'BSTINPUTS'} = './template/upstream/bibtex//:' . ($ENV{'BSTINPUTS'} // '');
