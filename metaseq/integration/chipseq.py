"""
This module integrates parts of metaseq that are useful for ChIP-seq analysis.
"""
from itertools import izip
import gffutils
from gffutils.helpers import asinterval
import metaseq
import pybedtools
from metaseq.minibrowser import SignalMiniBrowser, GeneModelMiniBrowser
import numpy as np
from matplotlib import pyplot as plt
import matplotlib


class GeneChipseqMiniBrowser(GeneModelMiniBrowser):
    def __init__(self, genomic_signal_objs, db, **kwargs):
        super(GeneChipseqMiniBrowser, self).__init__(genomic_signal_objs, db, **kwargs)

    def plot(self, feature):
        super(GeneChipseqMiniBrowser, self).plot(feature)
        ax1, ax2 = self.fig.axes
        ax1.legend(loc='best')
        ax1.set_ylabel('RPMMR')
        ax1.xaxis.set_visible(False)
        ax2.xaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter('%d'))
        ax2.set_xlabel(feature.chrom)


class SignalChipseqMiniBrowser(SignalMiniBrowser):
    def __init__(self, genomic_signal_objs, **kwargs):
        super(SignalChipseqMiniBrowser, self).__init__(genomic_signal_objs, **kwargs)

    def plot(self, feature):
        super(SignalChipseqMiniBrowser, self).plot(feature)
        ax1, = self.fig.axes
        ax1.legend(loc='best')
        ax1.set_ylabel('RPMMR')
        #ax1.xaxis.set_visible(False)
        #ax2.xaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter('%d'))
        ax1.set_xlabel(feature.chrom)


class Chipseq(object):
    """
    Class for visualizing and interactively exploring ChIP-seq data.

    Needs two BAM files (for IP and control) and a gffutils database
    filename in order to display gene models.

    Typical usage is to create a normalized array of signal over each
    feature with the `diff_array` method, and then plot with the `plot`
    method.

    The resulting figure has the matrix as a heatmap, the average signal
    over features, and a panel with points that can be zoomed and clicked,
    spawning a mini-browser window for the corresponding feature.

    Configuration can be done by adjusting the following attributes after
    creating a Chipseq instance:

        * `_strip_kwargs` (the style for the dots in the left panel)
        * `browser_plotting_kwargs` (style of signal lines in the mini-browser)

    Example usage:

        >>> dbfn=metaseq.example_filename(
        ...        'Homo_sapiens.GRCh37.66.cleaned.gtf.db')
        >>> C = Chipseq(
        ...        ip_bam=metaseq.example_filename(
        ...            'wgEncodeUwTfbsK562CtcfStdAlnRep1.bam'),
        ...        control_bam=metaseq.example_filename(
        ...            'wgEncodeUwTfbsK562InputStdAlnRep1.bam'),
        ...        dbfn=dbfn)
        >>> local_coverage_kwargs = dict(
        ...         fragment_size=200,
        ...         bins=100, chunksize=50, processes=6)

        >>> # make some features to use
        >>> G = gffutils.FeatureDB(dbfn)
        >>> genes = G.features_of_type('gene')
        >>> features = []
        >>> for i in range(100):
        ...    features.append(asinterval(genes.next()))

        >>> # x-axis for plots
        >>> x = np.arange(100)

        >>> # Create the array
        >>> C.diff_array(features=features, array_kwargs=local_coverage_kwargs)

        >>> # sort genes by
        >>> row_order = np.argsort(
        ...     plotutils.tip_zscores(C.diffed_array))[::-1]
        >>> C.plot(x=x, row_order=row_order)
        >>> plt.show()

    """
    def __init__(self, ip_bam, control_bam, dbfn=None):
        """
        Set up a :class:`Chipseq` object.


        :param ip_bam: filename of BAM file for ChIP data
        :param control_bam: filename of BAM file for control data
        :param dbfn: filename of gffutils database
        """
        self.ip = metaseq.genomic_signal(ip_bam, kind='bam')
        self.control = metaseq.genomic_signal(control_bam, kind='bam')
        self.dbfn = dbfn
        self.db = None
        if self.dbfn:
            self.db = gffutils.FeatureDB(dbfn)
        self.ip_array = None
        self.control_array = None

        self._strip_kwargs = dict(color='.5', markeredgewidth=0, marker='o',
                linestyle='None', picker=5)
        self.browser_plotting_kwargs = [
                dict(color='r', label='IP'),
                dict(color='k', linestyle=':', label='control')
                ]

    def diff_array(self, features, force=True, func=None,
            array_kwargs=dict()):
        """
        Scales the control and IP data to million mapped reads, then subtracts
        scaled control from scaled IP, applies `func(diffed)` to the diffed
        array, and finally sets `self.diffed_array` to be the result.

        Arrays `self.ip` and `self.control` are set as well, and if
        `force=False`, then previously-created arrays will be used instead of
        re-calculating new ones.  This is useful if you want to easily try
        multiple `func` functions without having to re-calculate the data.

        Another side-effect is that `self.features` is set so that it can be
        accesed by other methods.

        :param features: a list of pybedtools.Interval objects
        :param array_kwargs: extra keyword args passed to genomic_signal.array;
            typically this will include `bins`, `processes`, and `chunksize`
            arguments.
        :param func: a function to apply to the diffed arrays. By default
            this is :func:`metaseq.plotutils.nice_log`; another option might be
            `lambda x: x`, or `lambda x: 1e6*x`
        :param force: Force a re-calculation of the arrays; otherwise uses
            cached values
        """
        self.features = list(features)
        self.browser_local_coverage_kwargs = array_kwargs.copy()
        self.browser_local_coverage_kwargs.pop('processes')
        self.browser_local_coverage_kwargs.pop('chunksize')

        if (self.ip_array is None) or force:
            self.ip_array = self.ip.array(features, **array_kwargs)
            self.ip_array /= self.ip.million_mapped_reads()

        if (self.control_array is None) or force:
            self.control_array = self.control.array(features, **array_kwargs)
            self.control_array /= self.control.million_mapped_reads()

        if func is None:
            func = metaseq.plotutils.nice_log
        self.diffed_array = func(self.ip_array - self.control_array)

    def plot(self, x, row_order=None, imshow_kwargs=None):
        """
        Plot the scaled ChIP-seq data.

        :param x: X-axis to use (e.g, for TSS +/- 1kb with 100 bins, this would
            be `np.linspace(-1000, 1000, 100)`)
        :param row_order: Array-like object containing row order -- typically
            the result of an `np.argsort` call.
        """
        nrows = self.diffed_array.shape[0]
        if row_order is None:
            row_order = np.arange(nrows)
        extent = (min(x), max(x), 0, nrows)
        axes_info = metaseq.plotutils.matrix_and_line_shell(strip=True)
        fig, matrix_ax, line_ax, strip_ax, cbar_ax = axes_info
        _imshow_kwargs = dict(
                aspect='auto', extent=extent, interpolation='nearest')
        if imshow_kwargs:
            _imshow_kwargs.update(imshow_kwargs)

        mappable = matrix_ax.imshow(
                self.diffed_array[row_order],
                **_imshow_kwargs)
        plt.colorbar(mappable, cbar_ax)
        line_ax.plot(x, self.diffed_array.mean(axis=0))
        line, = strip_ax.plot(np.zeros((nrows,)), np.arange(nrows) + 0.5,
                **self._strip_kwargs)
        line.features = self.features
        line.ind = row_order

        matrix_ax.axis('tight')
        strip_ax.xaxis.set_visible(False)
        matrix_ax.yaxis.set_visible(False)
        matrix_ax.xaxis.set_visible(False)

        if self.db:
            self.minibrowser = GeneChipseqMiniBrowser(
                    [self.ip, self.control],
                    db=self.db,
                    plotting_kwargs=self.browser_plotting_kwargs,
                    local_coverage_kwargs=self.browser_local_coverage_kwargs)
        else:
            self.minibrowser = SignalChipseqMiniBrowser(
                    [self.ip, self.control],
                    plotting_kwargs=self.browser_plotting_kwargs,
                    local_coverage_kwargs=self.browser_local_coverage_kwargs)

        fig.canvas.mpl_connect('pick_event', self.callback)

        self.fig = fig
        self.axes = {
                'matrix_ax': matrix_ax,
                 'strip_ax': strip_ax,
                  'line_ax': line_ax,
                  'cbar_ax': cbar_ax
                }

    def callback(self, event):
        """
        Callback function to spawn a mini-browser when a feature is clicked.
        """
        artist = event.artist
        ind = artist.ind
        limit = 5
        browser = True
        if len(event.ind) > limit:
            print "more than %s genes selected; not spawning browsers" % limit
            browser = False
        for i in event.ind:
            feature = artist.features[ind[::-1][i]]
            print feature,
            if browser:
                self.minibrowser.plot(feature)


def estimate_shift(signal, genome=None, windowsize=5000, thresh=None,
        nwindows=1000, maxlag=500, array_kwargs=None, verbose=False):
    """
    Experimental: cross-correlation to estimate the shift width of ChIP-seq
    data

    This can be interpreted as the binding site footprint.

    For ChIP-seq, the plus and minus strand reads tend to be shifted in the 5'
    direction away from each other.  Various ChIP-seq peak-callers estimate
    this distance; this function provides a quick, tunable way to do so using
    cross-correlation.  The resulting shift can then be incorporated into
    subsequent calls to `array` by adding the shift_width kwarg.


    :param signal: genomic_signal object
    :param genome: String assembly for constructing windows
    :param nwindows: Number of windows to compute cross-correlation on
    :param windowsize: Size of each window to compute cross-correlation on.
    :param thresh: Threshold read coverage to run cross-correlation on.  This
        is likely to be a function of the fragment size provided in
        `array_kwargs` `windowsize`.  If `thresh` is small, then the cross
        correlation can be noisy.
    :param maxlag: Max shift to look for
    :param array_kwargs: Kwargs passed directly to genomic_signal.array, with
        the default of `bins=windowsize` for single-bp resolution, and
        `read_strand` will be overwritten.
    :param verbose: Be verbose.

    Returns lags and a `maxlag*2+1` x `nwindows` matrix of cross-correlations.

    You can then plot the average cross-correlation function with::

        plt.plot(lags, shift.mean(axis=0))

    and get the distance to shift with::

        d = lags[np.argmax(shift.mean(axis=0))]

    and then plot that with::

        plt.axvline(d, color='k', linestyle='--')

    The number of windows with at least `thresh` coverage is::

        shift.shape[0]
    """
    if thresh is None:
        thresh = 0

    if genome is None:
        genome = signal.genome()

    if array_kwargs is None:
        array_kwargs = {}

    array_kwargs.pop('read_strand', None)

    if 'bins' not in array_kwargs:
        array_kwargs['bins'] = windowsize

    def add_strand(f, strand):
        fields = f.fields[:]
        while len(fields) < 5:
            fields.append('.')
        fields.append(strand)
        return pybedtools.create_interval_from_list(fields)

    windows = pybedtools.BedTool()\
            .window_maker(genome=genome, w=windowsize)

    random_subset = pybedtools.BedTool(windows[:nwindows])\
            .shuffle(genome=genome).saveas()

    if verbose:
        sys.stderr.write("Getting plus-strand signal for %s regions...\n"\
                % nwindows)
        sys.stderr.flush()

    plus = signal.array(
            features=random_subset,
            read_strand="+",
            **array_kwargs).astype(float)

    if verbose:
        sys.stderr.write("Getting minus-strand signal for %s regions...\n"\
                % nwindows)
        sys.stderr.flush()

    minus = signal.array(
            features=random_subset,
            read_strand="-",
            **array_kwargs).astype(float)

    # only do cross-correlation if you have enough reads to do so
    enough = ((plus.sum(axis=1) / windowsize) > thresh) \
            & ((minus.sum(axis=1) / windowsize) > thresh)

    if verbose:
        sys.stderr.write(
                "Running cross-correlation on %s regions that passed "
                "threshold\n" % sum(enough))
    results = np.zeros((sum(enough), 2 * maxlag + 1))
    for i, xy in enumerate(izip(plus[enough], minus[enough])):
        x, y = xy
        results[i] = xcorr(x, y, maxlag)

    lags = np.arange(-maxlag, maxlag + 1)

    return lags, results


def xcorr(x, y, maxlags):
    """
    Streamlined version of matplotlib's `xcorr`, without the plots.

    :param x, y: NumPy arrays to cross-correlate
    :param maxlags: Max number of lags; result will be `2*maxlags+1` in length
    """
    xlen = len(x)
    ylen = len(y)
    assert xlen == ylen

    c = np.correlate(x, y, mode=2)

    # normalize
    c /= np.sqrt(np.dot(x, x) * np.dot(y, y))

    lags = np.arange(-maxlags, maxlags + 1)
    c = c[xlen - 1 - maxlags:xlen + maxlags]

    return c


if __name__ == "__main__":
    import sys
    choices = ['xcorr', 'chipseq']
    try:
        examples = sys.argv[1:]
    except IndexError:
        print 'Choices are: ', choices
        examples = []

    for ex in examples:
        if ex not in choices:
            raise ValueError('%s not in %s' % (ex, choices))

    if 'xcorr' in examples:
        ip = metaseq.genomic_signal(
                metaseq.example_filename(
                    'wgEncodeUwTfbsK562CtcfStdAlnRep1.bam'), 'bam')

        NWINDOWS = 5000
        FRAGMENT_SIZE = 1
        WINDOWSIZE = 5000
        THRESH = FRAGMENT_SIZE / float(WINDOWSIZE) * 10
        lags, shift = estimate_shift(
                ip, nwindows=NWINDOWS, maxlag=500, thresh=THRESH,
                array_kwargs=dict(
                    processes=8, chunksize=100,
                    fragment_size=FRAGMENT_SIZE),
                verbose=True)
        plt.plot(lags, shift.mean(axis=0))
        plt.axvline(
                lags[np.argmax(shift.mean(axis=0))],
                linestyle='--', color='k')

    if 'chipseq' in examples:
        # Example files...
        dbfn = metaseq.example_filename(
                'Homo_sapiens.GRCh37.66.cleaned.gtf.db')
        C = Chipseq(
                ip_bam=metaseq.example_filename(
                    'wgEncodeUwTfbsK562CtcfStdAlnRep1.bam'),
                control_bam=metaseq.example_filename(
                    'wgEncodeUwTfbsK562InputStdAlnRep1.bam'),
                dbfn=dbfn)

        # Make some features to use (TSS +/- 1kb)
        def generator():
            G = gffutils.FeatureDB(dbfn)
            genes = G.features_of_type('gene')
            for i in range(5000):
                yield asinterval(genes.next())

        from pybedtools.featurefuncs import TSS
        features = pybedtools.BedTool(generator())\
                .each(TSS, upstream=1000, downstream=1000)\
                .saveas()

        # x-axis for plots
        x = np.linspace(-500, 500, 100)

        # Create the array
        C.diff_array(features=features,
                array_kwargs=dict(
                    fragment_size=200, bins=100, chunksize=50, processes=6))

        # sort genes by TIP zscore
        row_order = np.argsort(
                metaseq.plotutils.tip_zscores(C.diffed_array))[::-1]

        # Plot 'em using a nice red-to-blue colormap
        from metaseq.colormap_adjust import smart_colormap
        cmap = smart_colormap(C.diffed_array.min(), C.diffed_array.max())

        C.plot(x=x, row_order=row_order, imshow_kwargs=dict(cmap=cmap))
    plt.show()
