"""
mint_export_reader - a small convenience library for analyzing export CSVs from Mint.com
"""

import pandas as pd
import numpy as np

class TransactionsExport:
    """
    This really just wraps a pandas DataFrame.
    """

    @staticmethod
    def from_file( export_file ):
        """Create a TransactionsExport from file

        Given a file path, initialize a TransactionsExport.

        Parameters
        ----------
        export_file : str or file object
            Export CSV to load.
        """
        df = pd.read_csv( export_file )

        # Create an "amount" column, which combines the "Amount" and "Transaction Type" columns
        # Then, drop those columns
        sign = np.ones( len( df ) )
        sign[ df[ "Transaction Type" ] == "debit" ] = -1
        df[ "amount" ] = sign * df[ "Amount" ]
        df.drop( [ "Amount", "Transaction Type" ], axis="columns", inplace=True )

        # Replace Date with a proper date index
        df[ "date" ] = pd.to_datetime( df[ "Date" ] )
        df.drop( "Date", axis="columns", inplace=True )

        # Rename the others
        df.rename( { "Account Name": "account",
                     "Category": "category",
                     "Description": "description",
                     "Original Description": "original_description",
                     "Labels": "labels",
                     "Notes": "notes" }, axis=1, inplace=True )

        # Create the object
        return TransactionsExport( df )

    def __init__( self, df ):
        """Don't use this, use TransactionsExport.from_file()"""
        self.df = df

    def __repr__( self ):
        """print the inner DF"""
        return str( self.df )

    def search( self, regex, invert=False ):
        """Find transactions matching a regex.

        Search each transactions descriptions for a given regex, and
        return a TransactionsExport with the matching (or
        non-matching) transactions.

        Parameters
        ----------
        regex : str
            The regular expression to apply to description and
            original description.
        invert : bool
            Whether to invert the match logic, returning only
            transactions which do not match.

        Returns
        -------
        matched_transactions : TransactionsExport
            The matching transactions.

        """
        msk = self.df.description.str.contains( regex, case=False )
        msk |= self.df.original_description.str.contains( regex, case=False )
        if invert:
            msk = ~msk
        return TransactionsExport( self.df[ msk ].copy() )

    def income( self ):
        """Filter only positive valued transactions.

        Return a TransactionsExport containing only the positive
        valued transactions.

        Returns
        -------
        ret : TransactionsExport
            The filtered transactions
        """
        return TransactionsExport( self.df[ self.df.amount > 0 ].copy() )

    def expenses( self ):
        """Filter only non-positive valued transactions.

        Return a TransactionsExport containing only the negative
        and zero valued transactions.

        Returns
        -------
        ret : TransactionsExport
            The filtered transactions
        """
        return TransactionsExport( self.df[ self.df.amount <= 0 ].copy() )

    def transfers( self, invert=False, time_window=None, allow_internal=True ):
        """Filter for transactions which are part of transfer pairs.

        A "transfer pair" is a pair of transactions satisfying the
        following conditions:
        - Same amount with different sign (e.g. $5.23 and $-5.23)
        - Occurring around the same time

        Note that this does not use Mint's "Transfer" category at all.
        Our definition intentionally includes things like simple
        refunds (one-item purchase followed by it being refunded for
        the exact amount). It also includes credit card payments, loan
        payments, and so on.

        By default, it also allows transfers within accounts, which
        removes spurious pseudo-transactions caused by things like
        changing stock portfolios. This cane be disabled with
        allow_internal=False.

        With invert=True, retain only transactions which are not
        transfer transactions. This is the more useful application.

        Finally, this is a little slow. There's probably a clever
        way to replace the itertuples() call with some vectorized
        operation. Optimizations welcome.

        Parameters
        ----------
        invert : bool
            If True, return only non-transfer transactions.
        time_window : None or pandas timedelta
            Override the default window to search for duplicate
            transactions. If not given, one week is used.
        allow_internal : bool
            Whether or not a transfer pair can consist of transactions
            in the same account.

        Returns
        -------
        ret : TransactionsExport
            The filtered transactions.

        """
        time_window = time_window or pd.to_timedelta( "7d" )
        transfer_transaction_mask = np.zeros( len( self.df ) ).astype( bool )
        for i, row in enumerate( self.df.itertuples() ):

            #
            # If this was already marked as a half of a transfer transaction, then skip it
            #
            if transfer_transaction_mask[ i ]:
                continue

            #
            # Find all matching transactions, narrowing cheaply/quickly first
            #
            df = self.df
            not_already_marked_msk = ~transfer_transaction_mask
            df = df[ not_already_marked_msk ]
            opposite_cost_msk = ( df.amount == -row.amount )
            df = df[ opposite_cost_msk ]

            if not allow_internal:
                # Not allowed to have internal transfers -- take only transactions from other accounts
                diff_account_msk = df.account != row.account
                df = df[ diff_account_msk ]

            in_range_msk = ( df.date - row.date ).abs() <= time_window
            df = df[ in_range_msk ]

            #
            # At least one transaction could qualify as a transaction pair
            # Take the first & move on
            #
            if len( df ) > 0:
                transfer_transaction_mask[ self.df.index.get_loc( row.Index ) ] = True
                transfer_transaction_mask[ self.df.index.get_loc( df.index[0] ) ] = True

        if invert:
            transfer_transaction_mask = ~transfer_transaction_mask
        return TransactionsExport( self.df[ transfer_transaction_mask ].copy() )

    def accounts( self ):
        """Get all accounts in this export.

        Get all of the accounts in this export.

        Returns
        -------
        ret : collection of str
            Collection of all unique account names.
        """
        return self.df.account.unique()

    def categories( self ):
        """Get all categories in this export.

        Get all of the categories in this export.

        Returns
        -------
        ret : collection of str
            Collection of all unique categories here.
        """
        return self.df.category.unique()

    def descriptions( self ):
        """Get all descriptions in this export.

        Get all of the descriptions in this export.

        Returns
        -------
        ret : collection of str
            Collection of all unique descriptions here.
        """
        return self.df.description.unique()

    def original_descriptions( self ):
        """Get all original_descriptions in this export.

        Get all of the original descriptions in this export.

        Returns
        -------
        ret : collection of str
            Collection of all unique original descriptions here.
        """
        return self.df.original_description.unique()

    def when( self, after=None, before=None, invert=False ):
        """Filter by date or date range.

        Filter for transactions happening within a date range. If
        after is given, then remove transactions occurring before that
        date. If before is given, then remove transactions occurring
        on or after that date. If both are given, return the
        transactions between.

        Both parameters are passed into pd.to_datetime(), so whatever
        that function accepts is cool.

        If invert is True, return the transactions which wouldn't match.

        Parameters
        ----------
        after : str or datetime-like
            See function docs
        before : str or datetime-like
            See function docs
        invert : bool
            If True, return only transactions outside the defined
            date range.

        Returns
        -------
        ret : TransactionsExport
            Filtered transactions
        """
        msk = np.ones( len( self.df ) ).astype( bool )
        if after is not None:
            after = pd.to_datetime( after )
            msk &= self.df.date >= after
        if before is not None:
            before = pd.to_datetime( before )
            msk &= self.df.date < before
        if invert:
            msk = ~msk
        return TransactionsExport( self.df[ msk ].copy() )

    def with_amount( self, above=None, below=None, invert=False ):
        """Filter by amount.

        Filter for transactions whose amount is above, below, or
        between some values.

        Parameters
        ----------
        above : None or float
            If given, only match values at or above this value.
        below : None or float
            If given, only match values below this value.
        invert : bool
            If True, return only transactions outside the defined
            price range.

        Returns
        -------
        ret : TransactionsExport
            The filtered transactions.
        """
        msk = np.ones( len( self.df ) ).astype( bool )
        if above is not None:
            msk &= self.df.amount >= above
        if below is not None:
            msk &= self.df.amount < below
        if invert:
            msk = ~msk
        return TransactionsExport( self.df[ msk ].copy() )

    def in_accounts( self, account_or_accounts, invert=False ):
        """Filter by accounts used.

        Remove all transactions in accounts other than those
        specified.

        Parameters
        ----------
        account_or_accounts : str or collection( str )
            The accounts to filter against
        invert : bool
            Whether to invert the match

        Returns
        -------
        ret : TransactionsExport
            The filtered transactions

        """
        if isinstance( account_or_accounts, str ):
            account_or_accounts = [ account_or_accounts ]
        msk = self.df.account.isin( account_or_accounts )
        if invert:
            msk = ~msk
        return TransactionsExport( self.df[ msk ].copy() )

    def recategorize( self, other, new_category, inplace=False ):
        """Change the category for a subset of transactions.

        Given another TransactionsExport, change the category of those
        transactions to a new value.

        Parameters
        ----------
        other : TransactionsExport
            The subset of transactions to recategorize
        new_category : str
            The new category
        inplace : bool
            Whether to edit the values in-place.

        Returns
        -------
        ret : TransactionsExport or None
            The edited transaction set. None if inplace=True.
        """
        if inplace:
            df = self.df
        else:
            df = self.df.copy()
        df.loc[ other.df.index, "category" ] = new_category
        if not inplace:
            return TransactionsExport( df )
        return None

    def in_categories( self, category_or_categories, invert=False ):
        """Filter by transaction category.

        Remove all transactions in categories other than those
        specified.

        Parameters
        ----------
        category_or_categories : str or collection( str )
            The categories to filter against
        invert : bool
            Whether to invert the match

        Returns
        -------
        ret : TransactionsExport
            The filtered transactions

        """
        if isinstance( category_or_categories, str ):
            category_or_categories = [ category_or_categories ]
        msk = self.df.category.isin( category_or_categories )
        if invert:
            msk = ~msk
        return TransactionsExport( self.df[ msk ].copy() )

    def total( self ):
        """Get the sum of all transactions.

        Returns
        -------
        sum : float
            The total of all transactions, in dollars.
        """
        return self.df.amount.sum()

    def by_category( self ):
        """Split by category.

        Returns
        -------
        ret : TransactionsExportCollection
            The transactions, split by category.
        """
        return TransactionsExportCollection( self.df.groupby( "category" ) )

    def by_account( self ):
        """Split by account.

        Returns
        -------
        ret : TransactionsExportCollection
            The transactions, split by account.
        """
        return TransactionsExportCollection( self.df.groupby( "account" ) )

    def by_description( self ):
        """Split by description.

        Returns
        -------
        ret : TransactionsExportCollection
            The transactions, split by description.
        """
        return TransactionsExportCollection( self.df.groupby( "description" ) )

    def by_original_description( self ):
        """Split by original description.

        Returns
        -------
        ret : TransactionsExportCollection
            The transactions, split by original description.
        """
        return TransactionsExportCollection( self.df.groupby( "original_description" ) )

    def yearly( self ):
        """Split by year.

        Returns
        -------
        ret : TransactionsExportCollection
            The transactions, split by year.
        """
        return TransactionsExportCollection( self.df.groupby( self.df.date.dt.year ) )

    def monthly( self ):
        """Split by month.

        Returns
        -------
        ret : TransactionsExportCollection
            The transactions, split by month.
        """
        return TransactionsExportCollection( self.df.groupby( pd.Grouper( key="date", freq='M' ) ) )

    def weekly( self ):
        """Split by week.

        Returns
        -------
        ret : TransactionsExportCollection
            The transactions, split by week.
        """
        return TransactionsExportCollection( self.df.groupby( pd.Grouper( key="date", freq='W' ) ) )

    def daily( self ):
        """Split by day.

        Returns
        -------
        ret : TransactionsExportCollection
            The transactions, split by day.
        """
        return TransactionsExportCollection( self.df.groupby( pd.Grouper( key="date", freq='d' ) ) )

    def __getattr__( self, attr ):
        """Forward all unknown APIs to the wrapped dataframe."""
        return getattr( self.df, attr )

class TransactionsExportCollection:
    """
    Represents a collection of `TransactionsExport` objects.

    This really just wraps a pandas GroupBy object.
    """

    def __init__( self, groupby ):
        self.groupby = groupby

    def totals( self ):
        """Total amounts for each subset.

        Return the total of all transactions in each subset.

        Returns
        -------
        totals : pd.Series of float
            The sum of the amount of all transactions in each subset.
            Index is the label defining each subset.
        """
        return self.groupby[ "amount" ].sum()

    def transaction_counts( self ):
        """Number of transactions for each subset.

        Return the number of transactions in each subset.

        Returns
        -------
        count : pd.Series of int
            The count of transactions in each subset. Index is the
            label defining each subset.
        """
        return self.groupby.size()

    def __getattr__( self, attr ):
        """Forward all unknown APIs to the wrapped groupby."""
        return getattr( self.groupby, attr )
