#   Copyright 2022 The PyMC Developers
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

# coding: utf-8
"""
Experimental probability distributions for stochastic nodes in PyMC.

The imports from pymc are not fully replicated here: add imports as necessary.
"""

from typing import List, Tuple, Union

import numpy as np
import pytensor.tensor as pt
from pymc import ChiSquared, CustomDist
from pymc.distributions import transforms
from pymc.distributions.dist_math import check_parameters
from pymc.distributions.distribution import Continuous
from pymc.distributions.shape_utils import rv_size_is_none
from pymc.logprob.utils import CheckParameterValue
from pymc.pytensorf import floatX
from pytensor.tensor.random.op import RandomVariable
from pytensor.tensor.variable import TensorVariable
from scipy import stats


class GenExtremeRV(RandomVariable):
    name: str = "Generalized Extreme Value"
    ndim_supp: int = 0
    ndims_params: List[int] = [0, 0, 0]
    dtype: str = "floatX"
    _print_name: Tuple[str, str] = ("Generalized Extreme Value", "\\operatorname{GEV}")

    def __call__(self, mu=0.0, sigma=1.0, xi=0.0, size=None, **kwargs) -> TensorVariable:
        return super().__call__(mu, sigma, xi, size=size, **kwargs)

    @classmethod
    def rng_fn(
        cls,
        rng: Union[np.random.RandomState, np.random.Generator],
        mu: np.ndarray,
        sigma: np.ndarray,
        xi: np.ndarray,
        size: Tuple[int, ...],
    ) -> np.ndarray:
        # Notice negative here, since remainder of GenExtreme is based on Coles parametrization
        return stats.genextreme.rvs(c=-xi, loc=mu, scale=sigma, random_state=rng, size=size)


gev = GenExtremeRV()


class GenExtreme(Continuous):
    r"""
    Univariate Generalized Extreme Value log-likelihood

    The cdf of this distribution is

    .. math::

       G(x \mid \mu, \sigma, \xi) = \exp\left[ -\left(1 + \xi z\right)^{-\frac{1}{\xi}} \right]

    where

    .. math::

        z = \frac{x - \mu}{\sigma}

    and is defined on the set:

    .. math::

        \left\{x: 1 + \xi\left(\frac{x-\mu}{\sigma}\right) > 0 \right\}.

    Note that this parametrization is per Coles (2001), and differs from that of
    Scipy in the sign of the shape parameter, :math:`\xi`.

    .. plot::

        import matplotlib.pyplot as plt
        import numpy as np
        import scipy.stats as st
        import arviz as az
        plt.style.use('arviz-darkgrid')
        x = np.linspace(-10, 20, 200)
        mus = [0., 4., -1.]
        sigmas = [2., 2., 4.]
        xis = [-0.3, 0.0, 0.3]
        for mu, sigma, xi in zip(mus, sigmas, xis):
            pdf = st.genextreme.pdf(x, c=-xi, loc=mu, scale=sigma)
            plt.plot(x, pdf, label=rf'$\mu$ = {mu}, $\sigma$ = {sigma}, $\xi$={xi}')
        plt.xlabel('x', fontsize=12)
        plt.ylabel('f(x)', fontsize=12)
        plt.legend(loc=1)
        plt.show()


    ========  =========================================================================
    Support   * :math:`x \in [\mu - \sigma/\xi, +\infty]`, when :math:`\xi > 0`
              * :math:`x \in \mathbb{R}` when :math:`\xi = 0`
              * :math:`x \in [-\infty, \mu - \sigma/\xi]`, when :math:`\xi < 0`
    Mean      * :math:`\mu + \sigma(g_1 - 1)/\xi`, when :math:`\xi \neq 0, \xi < 1`
              * :math:`\mu + \sigma \gamma`, when :math:`\xi = 0`
              * :math:`\infty`, when :math:`\xi \geq 1`
                where :math:`\gamma` is the Euler-Mascheroni constant, and
                :math:`g_k = \Gamma (1-k\xi)`
    Variance  * :math:`\sigma^2 (g_2 - g_1^2)/\xi^2`, when :math:`\xi \neq 0, \xi < 0.5`
              * :math:`\frac{\pi^2}{6} \sigma^2`, when :math:`\xi = 0`
              * :math:`\infty`, when :math:`\xi \geq 0.5`
    ========  =========================================================================

    Parameters
    ----------
    mu : float
        Location parameter.
    sigma : float
        Scale parameter (sigma > 0).
    xi : float
        Shape parameter
    scipy : bool
        Whether or not to use the Scipy interpretation of the shape parameter
        (defaults to `False`).

    References
    ----------
    .. [Coles2001] Coles, S.G. (2001).
        An Introduction to the Statistical Modeling of Extreme Values
        Springer-Verlag, London

    """

    rv_op = gev

    @classmethod
    def dist(cls, mu=0, sigma=1, xi=0, scipy=False, **kwargs):
        # If SciPy, use its parametrization, otherwise convert to standard
        if scipy:
            xi = -xi
        mu = pt.as_tensor_variable(floatX(mu))
        sigma = pt.as_tensor_variable(floatX(sigma))
        xi = pt.as_tensor_variable(floatX(xi))

        return super().dist([mu, sigma, xi], **kwargs)

    def logp(value, mu, sigma, xi):
        """
        Calculate log-probability of Generalized Extreme Value distribution
        at specified value.

        Parameters
        ----------
        value: numeric
            Value(s) for which log-probability is calculated. If the log probabilities for multiple
            values are desired the values must be provided in a numpy array or Pytensor tensor

        Returns
        -------
        TensorVariable
        """
        scaled = (value - mu) / sigma

        logp_expression = pt.switch(
            pt.isclose(xi, 0),
            -pt.log(sigma) - scaled - pt.exp(-scaled),
            -pt.log(sigma)
            - ((xi + 1) / xi) * pt.log1p(xi * scaled)
            - pt.pow(1 + xi * scaled, -1 / xi),
        )

        logp = pt.switch(pt.gt(1 + xi * scaled, 0.0), logp_expression, -np.inf)

        return check_parameters(
            logp, sigma > 0, pt.and_(xi > -1, xi < 1), msg="sigma > 0 or -1 < xi < 1"
        )

    def logcdf(value, mu, sigma, xi):
        """
        Compute the log of the cumulative distribution function for Generalized Extreme Value
        distribution at the specified value.

        Parameters
        ----------
        value: numeric or np.ndarray or `TensorVariable`
            Value(s) for which log CDF is calculated. If the log CDF for
            multiple values are desired the values must be provided in a numpy
            array or `TensorVariable`.

        Returns
        -------
        TensorVariable
        """
        scaled = (value - mu) / sigma
        logc_expression = pt.switch(
            pt.isclose(xi, 0), -pt.exp(-scaled), -pt.pow(1 + xi * scaled, -1 / xi)
        )

        logc = pt.switch(1 + xi * (value - mu) / sigma > 0, logc_expression, -np.inf)

        return check_parameters(
            logc, sigma > 0, pt.and_(xi > -1, xi < 1), msg="sigma > 0 or -1 < xi < 1"
        )

    def moment(rv, size, mu, sigma, xi):
        r"""
        Using the mode, as the mean can be infinite when :math:`\xi > 1`
        """
        mode = pt.switch(pt.isclose(xi, 0), mu, mu + sigma * (pt.pow(1 + xi, -xi) - 1) / xi)
        if not rv_size_is_none(size):
            mode = pt.full(size, mode)
        return mode


class Chi:
    r"""
    :math:`\chi` log-likelihood.

    The pdf of this distribution is

    .. math::

       f(x \mid \nu) = \frac{x^{\nu - 1}e^{-x^2/2}}{2^{\nu/2 - 1}\Gamma(\nu/2)}

    .. plot::
        :context: close-figs

        import matplotlib.pyplot as plt
        import numpy as np
        import scipy.stats as st
        import arviz as az
        plt.style.use('arviz-darkgrid')
        x = np.linspace(0, 10, 200)
        for df in [1, 2, 3, 6, 9]:
            pdf = st.chi.pdf(x, df)
            plt.plot(x, pdf, label=r'$\nu$ = {}'.format(df))
        plt.xlabel('x', fontsize=12)
        plt.ylabel('f(x)', fontsize=12)
        plt.legend(loc=1)
        plt.show()

    ========  =========================================================================
    Support   :math:`x \in [0, \infty)`
    Mean      :math:`\sqrt{2}\frac{\Gamma((\nu + 1)/2)}{\Gamma(\nu/2)}`
    Variance  :math:`\nu - 2\left(\frac{\Gamma((\nu + 1)/2)}{\Gamma(\nu/2)}\right)^2`
    ========  =========================================================================

    Parameters
    ----------
    nu : tensor_like of float
        Degrees of freedom (nu > 0).

    Examples
    --------
    .. code-block:: python
        import pymc as pm
        from pymc_experimental.distributions import Chi

        with pm.Model():
            x = Chi('x', nu=1)
    """

    @staticmethod
    def chi_dist(nu: TensorVariable, size: TensorVariable) -> TensorVariable:
        return pt.math.sqrt(ChiSquared.dist(nu=nu, size=size))

    def __new__(cls, name, nu, **kwargs):
        if "observed" not in kwargs:
            kwargs.setdefault("transform", transforms.log)
        return CustomDist(name, nu, dist=cls.chi_dist, class_name="Chi", **kwargs)

    @classmethod
    def dist(cls, nu, **kwargs):
        return CustomDist.dist(nu, dist=cls.chi_dist, class_name="Chi", **kwargs)


class Maxwell:
    R"""
    The Maxwell-Boltzmann distribution

    The pdf of this distribution is

    .. math::

       f(x \mid a) = {\displaystyle {\sqrt {\frac {2}{\pi }}}\,{\frac {x^{2}}{a^{3}}}\,\exp \left({\frac {-x^{2}}{2a^{2}}}\right)}

    Read more about it on `Wikipedia <https://en.wikipedia.org/wiki/Maxwell%E2%80%93Boltzmann_distribution>`_

    .. plot::
        :context: close-figs

        import matplotlib.pyplot as plt
        import numpy as np
        import scipy.stats as st
        import arviz as az
        plt.style.use('arviz-darkgrid')
        x = np.linspace(0, 20, 200)
        for a in [1, 2, 5]:
            pdf = st.maxwell.pdf(x, scale=a)
            plt.plot(x, pdf, label=r'$a$ = {}'.format(a))
        plt.xlabel('x', fontsize=12)
        plt.ylabel('f(x)', fontsize=12)
        plt.legend(loc=1)
        plt.show()

    ========  =========================================================================
    Support   :math:`x \in (0, \infty)`
    Mean      :math:`2a \sqrt{\frac{2}{\pi}}`
    Variance  :math:`\frac{a^2(3 \pi - 8)}{\pi}`
    ========  =========================================================================

    Parameters
    ----------
    a : tensor_like of float
        Scale parameter (a > 0).

    """

    @staticmethod
    def maxwell_dist(a: TensorVariable, size: TensorVariable) -> TensorVariable:
        if rv_size_is_none(size):
            size = a.shape

        a = CheckParameterValue("a > 0")(a, pt.all(pt.gt(a, 0)))

        return Chi.dist(nu=3, size=size) * a

    def __new__(cls, name, a, **kwargs):
        return CustomDist(
            name,
            a,
            dist=cls.maxwell_dist,
            class_name="Maxwell",
            **kwargs,
        )

    @classmethod
    def dist(cls, a, **kwargs):
        return CustomDist.dist(
            a,
            dist=cls.maxwell_dist,
            class_name="Maxwell",
            **kwargs,
        )


class GeneralizedNormalRV(RandomVariable):
    name: str = "Generalized Normal"
    ndim_supp: int = 0
    ndims_params: List[int] = [0, 0, 0]
    dtype: str = "floatX"
    _print_name: Tuple[str, str] = ("Generalized Normal", "\\operatorname{GenNorm}")

    def __call__(self, loc=0.0, alpha=1.0, beta=2.0, **kwargs) -> TensorVariable:
        return super().__call__(loc, alpha, beta, **kwargs)

    @classmethod
    def rng_fn(
        cls,
        rng: np.random.RandomState,
        loc: np.ndarray,
        alpha: np.ndarray,
        beta: np.ndarray,
        size: Tuple[int, ...],
    ) -> np.ndarray:
        return stats.gennorm.rvs(beta, loc=loc, scale=alpha, size=size, random_state=rng)

# Create the actual `RandomVariable` `Op`...
gennorm = GeneralizedNormalRV()


class GeneralizedNormal(Continuous):
    r"""
    Univariate Generalized Normal distribution

    The cdf of this distribution is

    .. math::
    

      G(x \mid \mu, \alpha, \beta) = \frac{1}{2} + \mathrm{sign}(x-\mu) \frac{1}{2\Gamma(1/\beta)} \gamma\left(1/\beta, \left|\frac{x-\mu}{\alpha}\right|^\beta\right)

    where :math:`\gamma()` is the unnormalized incomplete lower gamma function.

    The support of the function is the whole real line, while the parameters are defined as

    .. math::

    \alpha, \beta > 0

    This is the same parametrization used in Scipy and also follows
    `Wikipedia <https://en.wikipedia.org/wiki/Generalized_normal_distribution>`_

    The :math:`\beta` parameter controls the kurtosis of the distribution, where the excess
    kurtosis is given by

    .. math::

    \mathrm{exKurt}(\beta) = \frac{\Gamma(5/\beta) Gamma(1/\beta)}{\gamma(3/\beta)^2} - 3

    .. plot::

        :context: close-figs

        import matplotlib.pyplot as plt
        import numpy as np
        import scipy.stats as stats
        from cycler import cycler

        plt.style.use('arviz-darkgrid')
        x = np.linspace(-3, 3, 200)
        
        betas = [0.5, 2, 8]
        beta_cycle = cycler(color=['r', 'g', 'b'])
        alphas = [1.0, 2.0]
        alpha_cycle = cycler(ls=['-', '--'])
        cycler = beta_cycle*alpha_cycle
        icycler = iter(cycler)

        for beta in betas:
           for alpha in alphas:
              pdf = scipy.stats.gennorm.pdf(x, beta, loc=0.0, scale=alpha)
              args = next(icycler)
              plt.plot(x, pdf, label=r'$\alpha=$ {0}  $\beta=$ {1}'.format(alpha, beta), **args)
              plt.xlabel('x', fontsize=12)
              plt.ylabel('f(x)', fontsize=12)
              plt.legend(loc=1)
        plt.show()

    ========  =========================================================================
    Support   :math:`x \in (-\infty, \infty)`
    Mean      :math:`\mu`
    Variance  :math:`\frac{\alpha^2 \Gamma(3/\beta)}{\Gamma(1/\beta)}`
    ========  =========================================================================

    Parameters
    ----------
    Parameters
    ----------
    mu : float
        Location parameter.
    alpha : float
        Scale parameter (alpha > 0). Note that the variance of the distribution is
        not alpha squared. In particular, whene beta=2 (normal distribution), the variance
        is :math:`alpha^2/2`.
    beta : float
        Shape parameter (beta > 0). This is directly related to the kurtosis which is a
        monotonically decreasing function of beta

    """
    rv_op = gennorm

    @classmethod
    def dist(cls, mu, alpha, beta, **kwargs) -> RandomVariable:
        mu = pt.as_tensor_variable(floatX(mu))
        alpha = pt.as_tensor_variable(floatX(alpha))
        beta = pt.as_tensor_variable(floatX(beta))

        return super().dist([mu, alpha, beta], **kwargs)


    # moment here returns the mean
    def moment(rv, size, mu, alpha, beta):
        moment, *_ = pt.broadcast_arrays(mu, alpha, beta)
        if not rv_size_is_none(size):
            moment = pt.full(size, moment)
        return moment

    def logp(value, mu, alpha, beta):

        z = (value-mu)/alpha
        lp = pt.log(0.5*beta) - pt.log(alpha) - pt.gammaln(1.0/beta) - pt.pow(pt.abs(z), beta)

        return check_parameters(
            lp,
            alpha > 0,
            beta > 0,
            msg="alpha > 0, beta > 0",
        )


    def logcdf(value, mu, alpha, beta):
        """
        Compute the log of the cumulative distribution function for a Generalized
        Normal distribution

        Parameters
        ----------
        value: numeric or np.ndarray or `TensorVariable`
             Value(s) for which the log CDF is calculated
        alpha: numeric
             Scale parameter
        beta: numeric
             Shape parameter

        """

        
        z = pt.abs((value-mu)/alpha)
        c =  pt.sign(value-mu)

        # This follows the Wikipedia entry for the function - scipy has
        # opted for a slightly different version using gammaincc instead.
        # Note that on the Wikipedia page the unnormalised \gamma function
        # is used, while gammainc is a normalised function
        cdf = 0.5 + 0.5*pt.sign(value-mu)*pt.gammainc(1.0/beta, pt.pow(z, beta))

        return pt.log(cdf)
        
        

